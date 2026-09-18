# Security Games — Requirements

## Context

The games brick has a pluggable `GameRules` protocol. Today: Connect Four (strategy) and CTF Challenge (flag capture). Rubrics exist for XSS Hunter, IDOR Detective, and Finding Triage but no game adapters implement them. The team needs security-focused games that train agents to find real vulnerability classes — aligned with OWASP Top 10:2025 and PortSwigger's 30 vulnerability categories.

Games run in sandboxed environments (LocalStack AWS, Docker containers). Agents play by executing commands, reading code, and submitting findings. The game engine validates findings against ground truth and scores via Bedrock rubrics.

## Stakeholders

- Security team (primary consumers — agents that find vulns)
- ML team (RL training data from game transcripts)
- Platform team (sandbox infrastructure)

## Requirements

### R1: Vulnerability Game Adapters
Each adapter implements `GameRules` protocol. Agent actions: `analyze_code`, `trace_dataflow`, `submit_finding`, `check_config`, `test_endpoint`. Game validates against embedded ground truth.

#### R1.1: Injection Games (OWASP A05:2025)
- `sql_injection` — agent finds SQLi in parameterized/raw queries. Ground truth: vulnerable query + injection point.
- `xss_hunter` — agent traces source→sink XSS flows. Ground truth: DOM/reflected/stored XSS with sanitization context.
- `command_injection` — agent finds OS command injection. Ground truth: unsanitized shell exec.
- `ssti` — server-side template injection. Ground truth: template engine + injection point.

#### R1.2: Access Control Games (OWASP A01:2025)
- `idor_detective` — agent finds insecure direct object references. Ground truth: endpoints lacking ownership checks.
- `privilege_escalation` — agent finds vertical/horizontal privilege escalation paths. Ground truth: role bypass vectors.
- `path_traversal` — agent finds directory traversal. Ground truth: unsanitized file path input.

#### R1.3: Security Misconfiguration Games (OWASP A02:2025)
- `misconfiguration_hunter` — agent audits cloud/app config. Ground truth: open S3 buckets, debug endpoints, default creds, permissive CORS.

#### R1.4: Cryptographic Failure Games (OWASP A04:2025)
- `crypto_audit` — agent finds weak crypto: hardcoded keys, weak algorithms, missing TLS, plaintext secrets.

#### R1.5: Finding Triage Game
- `finding_triage` — agent classifies findings as TP/FP/needs-info against ground truth labels. Tests reasoning, not exploitation.

#### R1.6: Supply Chain Games (OWASP A03:2025)
- `dependency_audit` — agent analyzes dependency trees for known CVEs, typosquatting, malicious packages.

### R2: Ground Truth Format
Each game instance carries a ground truth payload:
```python
{
    "vulnerabilities": [
        {"id": "VULN-001", "type": "sqli", "location": "UserDAO.java:42",
         "severity": "high", "evidence": "...", "cwe": "CWE-89"}
    ],
    "false_positives": ["FP-001"],  # decoys the agent should NOT flag
    "difficulty": "medium",
    "category": "injection",
}
```

### R3: Scoring Dimensions
All security games score on 4 axes (0.0–1.0 each, averaged):
1. Correctness — did the agent find real vulns, not FPs?
2. Evidence — is the data flow / code reference complete?
3. Completeness — did it find ALL vulns, not just the obvious one?
4. Efficiency — how many actions before finding vs max allowed?

### R4: Sandbox Integration
Games that need runtime execution (SQLi, command injection) reference a `sandbox_env_id` in config. The sandbox brick provisions the environment. The game adapter is a pure rules engine — it doesn't execute code directly.

### R5: CWE/OCSF Taxonomy
Every ground truth vulnerability carries a CWE ID. Findings submitted by the agent are enriched with CWE classification via the security brick's taxonomy enrichment (already exists).

### R6: Difficulty Tiers
Each game type supports 3 difficulty tiers:
- Easy — single obvious vulnerability, no sanitization
- Medium — multiple vulns, some sanitization to bypass
- Hard — subtle vulns, defense-in-depth, decoy false positives
