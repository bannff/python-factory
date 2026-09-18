# Security Games — Tasks

## Task 1: SecurityGameRules base class
- [ ] Create `components/games/runtime/adapters/security_base.py`
- [ ] Implement shared `create_initial_state`, `legal_moves`, `apply_move`, `evaluate`
- [ ] Ground truth matching logic with fuzzy location comparison
- [ ] 4-axis scoring (correctness, evidence, completeness, efficiency)
- [ ] Hypothesis property tests for base class

## Task 2: Injection game adapters (OWASP A05)
- [ ] `sql_injection.py` — SQLInjectionRules
- [ ] `xss_hunter.py` — XSSHunterRules
- [ ] `command_injection.py` — CommandInjectionRules
- [ ] `ssti.py` — SSTIRules
- [ ] Each overrides `game_type` and optionally `_score_finding`
- [ ] Rubrics already exist for xss_hunter; add rubrics for sqli, cmdi, ssti

## Task 3: Access control game adapters (OWASP A01)
- [ ] `idor_detective.py` — IDORDetectiveRules
- [ ] `priv_esc.py` — PrivEscRules
- [ ] `path_traversal.py` — PathTraversalRules
- [ ] Rubric for idor_detective exists; add rubrics for priv_esc, path_traversal

## Task 4: Config/Crypto/Supply chain adapters (OWASP A02/A04/A03)
- [ ] `misconfig_hunter.py` — MisconfigRules
- [ ] `crypto_audit.py` — CryptoAuditRules
- [ ] `dependency_audit.py` — DependencyAuditRules
- [ ] Add rubrics for each

## Task 5: Finding triage adapter
- [ ] `finding_triage.py` — FindingTriageRules (rubric exists)
- [ ] Agent classifies findings as TP/FP/needs-info
- [ ] Score against ground truth labels

## Task 6: Ground truth scenarios
- [ ] Create `components/games/resources/scenarios/` directory
- [ ] 3 scenarios per game type (easy/medium/hard) — start with sqli, xss, idor
- [ ] YAML format with code_snippet, vulnerabilities, false_positives
- [ ] Scenario loader in security_base.py

## Task 7: Runtime registration
- [ ] Update `runtime.py._create_rules()` with all new game types
- [ ] Update `available_game_types()` to include all security games
- [ ] Update `server.py` capabilities and config schema

## Task 8: Tests
- [ ] Hypothesis property tests for each adapter (save/load/score roundtrips)
- [ ] E2E recipe: agent plays sql_injection game, submits finding, gets scored
- [ ] Verify game_pipeline processes security game results correctly
