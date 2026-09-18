# Security Games — Design

## Architecture

All security game adapters implement the existing `GameRules` protocol from `components/games/runtime/ports.py`. No protocol changes needed.

```
GameRules (Protocol)
├── ConnectFourRules      (existing)
├── CTFChallengeRules     (existing)
├── SQLInjectionRules     (new)
├── XSSHunterRules        (new)
├── CommandInjectionRules (new)
├── SSTIRules             (new)
├── IDORDetectiveRules    (new)
├── PrivEscRules          (new)
├── PathTraversalRules    (new)
├── MisconfigRules        (new)
├── CryptoAuditRules      (new)
├── FindingTriageRules    (existing rubric, new adapter)
└── DependencyAuditRules  (new)
```

## Shared Base: SecurityGameRules

All security games share common patterns. Extract a base class:

```python
# components/games/runtime/adapters/security_base.py (<200 LOC)

class SecurityGameRules:
    """Base for all security-focused game adapters."""

    game_type: str  # override in subclass
    default_max_actions: int = 20
    valid_actions: tuple[str, ...] = (
        "analyze_code", "trace_dataflow", "submit_finding",
        "check_config", "test_endpoint", "read_file", "execute",
    )

    def create_initial_state(self, game_id, config) -> GameState:
        # Common: embed ground_truth in config, set up action tracking
        ...

    def legal_moves(self, state) -> list[dict]:
        # Common: return valid_actions if game active and under max
        ...

    def apply_move(self, state, player, move) -> MoveResult:
        action = move["action"]
        if action == "submit_finding":
            return self._score_finding(state, move)
        # Other actions: record and return neutral reward
        ...

    def _score_finding(self, state, move) -> MoveResult:
        # Compare submitted finding against ground_truth
        # Partial credit for close matches (right file, wrong line)
        ...

    def evaluate(self, state) -> dict:
        # Compute 4-axis score from move history vs ground truth
        ...
```

Each concrete adapter overrides `game_type`, `valid_actions`, and optionally `_score_finding` for type-specific validation (e.g., SQLi checks for injection point syntax, XSS checks for source→sink trace).

## File Layout

```
components/games/runtime/adapters/
├── security_base.py          # Shared SecurityGameRules base
├── sql_injection.py          # SQLInjectionRules
├── xss_hunter.py             # XSSHunterRules
├── command_injection.py      # CommandInjectionRules
├── ssti.py                   # SSTIRules
├── idor_detective.py         # IDORDetectiveRules
├── priv_esc.py               # PrivEscRules
├── path_traversal.py         # PathTraversalRules
├── misconfig_hunter.py       # MisconfigRules
├── crypto_audit.py           # CryptoAuditRules
├── finding_triage.py         # FindingTriageRules
└── dependency_audit.py       # DependencyAuditRules
```

Each file <200 LOC. The base handles 80% of the logic.

## Ground Truth Scenarios

Scenarios are data, not code. Stored as YAML in `components/games/resources/scenarios/`:

```yaml
# scenarios/sqli/easy-001.yaml
game_type: sql_injection
difficulty: easy
description: "Find the SQL injection in the user search endpoint"
code_snippet: |
  def search_users(query):
      sql = f"SELECT * FROM users WHERE name LIKE '%{query}%'"
      return db.execute(sql)
vulnerabilities:
  - id: VULN-001
    type: sqli
    location: "search.py:2"
    cwe: CWE-89
    evidence: "f-string interpolation into SQL query"
    severity: high
false_positives: []
max_actions: 10
```

The `create_initial_state` method loads a scenario from config or picks a random one for the difficulty tier.

## Runtime Registration

`runtime.py._create_rules()` maps game_type strings to adapters:

```python
_SECURITY_GAMES = {
    "sql_injection": "sql_injection.SQLInjectionRules",
    "xss_hunter": "xss_hunter.XSSHunterRules",
    # ... etc
}
```

Lazy-loaded on first use. No startup cost for unused game types.

## Scoring Flow

```
Agent submits finding → SecurityGameRules._score_finding()
  → Compare against ground_truth.vulnerabilities (fuzzy match on location + type)
  → If match: reward +0.5 to +1.0 (scaled by evidence quality)
  → If false_positive match: reward -0.5 (penalize FP submission)
  → If no match: reward -0.1 (wrong finding)
  → If all vulns found: terminal=True, game finished

Post-game → game_pipeline.process_game_finished()
  → Graph: store transcript as GameSession + GameMove nodes
  → Blockchain: mint reward tokens for winner
  → Evals: score via Bedrock rubric (4-axis)
```

## Sandbox Integration

Games that need live execution (SQLi against a real DB, command injection in a container) set `sandbox_env_id` in config. The agent calls `sandbox_execute` MCP tool separately — the game adapter just records the action and validates findings. This keeps the game adapter pure (no I/O).

For LocalStack games (misconfiguration, S3 bucket audit), the sandbox brick provisions a LocalStack environment with pre-configured misconfigurations.
