# Protected Business Content Foundation and Email Capability

## Goal
Establish a reusable protected-content rail that intentionally retains searchable business content while preventing uncontrolled copies in Workflow, telemetry, agent memory, Evals, and provider error paths. Use it to complete the first provider-neutral email capability only after the protected-content controls pass.

## Scope and release boundary
This change implements local-first artifact contracts, encryption, no-copy Workflow handling, safe projections, and tests. It does **not** make online/shared email effects releasable: authenticated gateway identity/PEP (`python-factory-anb95`) remains a hard release prerequisite. Direct external effects fail closed when no trusted principal/tenant context is present.

## Ownership
- **Security:** versioned protected-content profiles, crypto/control validation, adversarial challenge fixtures, and release gates; never content storage/decryption.
- **mcp_utils:** domain-neutral strict DTOs, artifact reference grammar, protected-content sanitizer/projection interfaces; no imports of domain bricks.
- **Storage:** mandatory encrypted artifact data plane: immutable create-or-match, keyed fingerprint, opaque refs, retention/tombstone/rekey, authorized bounded projections/search.
- **Workflow:** opaque artifact bindings, fingerprints, attempts, policy/projection evidence, and receipts only; rejects protected inline payloads.
- **Integrations:** converts provider material into artifact requests and materializes authorized content in memory for one bounded effect.
- **Telemetry/Memory/Evals:** accept approved safe projections/refs only.
- **Auth/Permissions/Gateway:** trusted identity and policy enforcement; required before shared/online effects.

## Normative local crypto profile v1
The local protected artifact adapter uses `cryptography` primitives only:
- Canonical payload: UTF-8 `canonical_json` of strict typed artifact content.
- Per artifact: random 32-byte DEK; encrypt payload with AES-256-GCM and a fresh 12-byte nonce.
- Wrap DEK: AES-256-GCM under the active local KEK with an independent fresh 12-byte wrap nonce.
- AAD: canonical JSON containing immutable `{artifact_id, tenant_id, owner_principal_id, artifact_kind, schema_version, profile_version, key_id}`. Any metadata substitution fails authentication.
- Key provider: typed local provider resolves `FACTORY_PROTECTED_CONTENT_LOCAL_KEK` as base64-encoded exactly 32-byte key and an explicit key id. Missing/malformed/revoked key fails closed. Test provider is explicit test-only and never selected by request data.
- Content equality: tenant-scoped HMAC-SHA256 fingerprint over canonical plaintext using a provider-derived index key; it is used for create-or-match/idempotency and never serves as a public artifact id. Artifact refs are random opaque IDs.
- Envelope fields are versioned, length-validated, and encoded with base64url. Historical key IDs remain decryptable through provider lookup for rekey; interrupted rekey leaves the prior valid envelope intact.

## Shared contract
Add strict versioned `ProtectedContentDescriptor`, `ProtectedArtifactRef`, `ProtectedContentProjection`, and `ProtectedContentPolicyProfile` vocabulary in `mcp_utils`. Descriptor includes classification, purpose, tenant/owner, kind/schema/profile version, retention, and allowed projection profile. Callers cannot select encryption on/off or arbitrary projections.

## Storage contract
Add a typed `BusinessContentArtifactStore` port and encrypted local SQLite adapter. It supports immutable create-or-match, owner/tenant/purpose-scoped materialize, bounded authorized search/projection, tombstone/retention/rekey. Generic document/blob MCP tools are not the protected artifact path. Protected writes fail if the chosen deployment profile cannot honor encryption.

## Identity/authorization
Artifact create/read/search/materialize/tombstone/rekey require a trusted envelope-derived principal and tenant. The concrete PEP is out of scope, but Storage and Integrations must require a typed authorization assertion/ambient trusted identity abstraction and fail closed if absent. The future gateway/Permissions PEP decision inputs are `{principal, tenant, action, artifact metadata, purpose, projection_profile}`. Owner/tenant fields from tool input are never authoritative.

## Workflow and integration path
Create/match protected content before Workflow. Task payload holds only artifact ref, fingerprint, descriptor/schema/profile version, connection ref, and action identity. Workflow snapshot/run/task/event/evidence sanitization rejects protected inline content and persists no body, subject, recipient, raw query, attachment bytes, provider request, or provider response. Retry re-materializes the same verified artifact under frozen identity/purpose and forwards the same attempt idempotency key to Integrations. Integrations sends provider-neutral content in memory and returns safe receipt only.

## Sanitizer/telemetry
A shared protected-content sanitizer is mandatory at typed tool ingress/egress, Workflow persistence/events/evidence, telemetry/exporter capture, error conversion, Memory, and Evals. It recursively replaces/rejects protected values before serialization; truncation is not redaction. Safe projections are allowlisted server-side and bounded.

## Required tests
1. Crypto: fresh DEK/nonce, ciphertext contains no canary plaintext, malformed/truncated/swapped ciphertext/wrapped-DEK/AAD metadata fails with one opaque error; rotation/rekey and interrupted rekey preserve valid old read or fail closed.
2. Create-or-match: concurrent identical creates yield one artifact; same ref/fingerprint with changed content conflicts; no partial artifact/key material after interruption.
3. Authorization: owner/tenant/purpose/projection substitution and forged/expired/tombstoned ref fail without existence leakage.
4. No-copy: recursive SQLite/file/Workflow/event/evidence/MCP/telemetry/Memory/Evals scans of Unicode/multiline/base64/JSON-escaped canaries never contain recipient/subject/body/attachment/query/provider raw data.
5. Retry: timeout-before/after-send, restart, duplicate request, tampered/deleted/expired artifact retain same ref/fingerprint/idempotency or fail before provider call.
6. Search: bounded safe projection only, no unauthorized hit counts/snippets/cursor reuse, and same path works for email plus non-email fixture.
7. Hypothesis RuleBasedStateMachine covers create/match, materialize, search, expiry/tombstone, rekey, retry, and owner isolation.

## Explicitly out of scope
Live Google OAuth/client credentials, production KMS/HSM, online/shared gateway auth implementation, policy UI, marketplace, unbounded/full-text/vector search, attachment extraction, and migration of old plaintext rows.
