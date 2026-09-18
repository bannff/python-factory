# RL Training Pipeline — Design

## Architecture

No new bricks. This is a wiring layer that connects existing bricks via MCP tools. The pipeline lives in the games brick as `runtime/training_pipeline.py` (orchestrator) and `runtime/transcript_extractor.py` (graph → JSONL).

```
┌─────────┐    ┌───────────┐    ┌──────────┐    ┌────────┐
│  Graph   │───→│ Extractor │───→│ ML Brick │───→│Storage │
│(transcripts)  │(→ JSONL)  │    │(QLoRA)   │    │(ckpts) │
└─────────┘    └───────────┘    └──────────┘    └────────┘
      ↑                              │
      │         ┌──────────┐         │
      └─────────│Convergence│←───────┘
                └──────────┘
                     │
              ┌──────┴──────┐
              │   Memory    │  (training insights)
              │   KB        │  (strategy docs)
              └─────────────┘
```

All cross-brick calls go through the MCP tool invoker. No direct imports.

## Component 1: Transcript Extractor

`components/games/runtime/transcript_extractor.py` (<200 LOC)

```python
def extract_transcripts(
    game_type: str | None = None,
    min_eval_score: float = 0.0,
    since: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query graph for finished GameSession nodes, return training examples."""
    # 1. graph_find_entities(entity_type="GameSession", limit=limit)
    # 2. Filter: status=="finished", game_type match, created_at >= since
    # 3. For each game: graph_get_neighbors(game_id, "HAS_MOVE")
    # 4. Convert to training examples with reward shaping
    ...

def to_training_jsonl(transcripts: list[dict]) -> str:
    """Convert transcripts to JSONL training format."""
    # Each move becomes a training example:
    # {"input": state_before_move, "output": move_taken, "reward": shaped_reward}
    ...

def shape_rewards(
    moves: list[dict], terminal_reward: float, gamma: float = 0.95,
) -> list[float]:
    """Discount terminal reward back through move sequence."""
    # rewards[i] = terminal_reward * gamma^(n-i)
    ...
```

## Component 2: Training Pipeline

`components/games/runtime/training_pipeline.py` (<200 LOC)

```python
def run_training_cycle(
    game_type: str,
    model_id: str = "mlx-community/Llama-3.2-1B-Instruct-4bit",
    min_eval_score: float = 0.3,
    max_iterations: int = 50,
) -> dict:
    """One full RL training cycle."""
    # 1. Extract transcripts from graph
    # 2. Convert to JSONL
    # 3. Store dataset via storage brick
    # 4. Create ML dataset pipeline
    # 5. Run fine-tuning job
    # 6. Record convergence score
    # 7. Store training insight in memory
    # 8. Return cycle results
    ...
```

## Component 3: MCP Tools

Two new operational tools in `components/games/mcp/operational.py`:

```python
@operational
def games_extract_transcripts(
    game_type: str | None = None,
    min_eval_score: float = 0.0,
    since: str | None = None,
    limit: int = 100,
    format: str = "jsonl",
) -> dict:
    """Extract game transcripts as training data."""

@operational
def games_run_training_cycle(
    game_type: str,
    model_id: str = "",
    min_eval_score: float = 0.3,
) -> dict:
    """Run one RL training cycle: extract → train → evaluate."""
```

## Data Storage Design

### Graph (Neo4j) — Relationships & Lineage
```
(GameSession)-[:HAS_MOVE]->(GameMove)
(GameSession)-[:SCORED_BY]->(EvalResult)
(GameSession)-[:REWARDED_BY]->(BountyTransaction)
(TrainingBatch)-[:TRAINED_ON]->(GameSession)
(TrainingBatch)-[:PRODUCED]->(ModelCheckpoint)
```
Why graph: these are relationship-heavy entities. "Which games trained this model?" "What's the win rate trend for SQLi games?" — graph queries.

### Memory (Neo4j HNSW) — Agent Learning
```python
# After each training batch:
memory_store(
    content="SQLi training batch 7: 50 games, win rate 0.6→0.72. "
            "Key insight: agents that call analyze_code before submit_finding "
            "score 40% higher on evidence dimension.",
    user_id="kiro-agent",
    metadata={"type": "training_insight", "game_type": "sql_injection",
              "batch_id": "batch-007", "win_rate": 0.72}
)
```
Why memory: these are semantic, retrievable insights. An agent starting a new SQLi game can `memory_retrieve("sql injection strategy tips")` and get accumulated wisdom.

### KB (Neo4j + Bedrock GraphRAG) — Reference Knowledge
```python
# One-time ingestion of strategy guides:
kb_ingest(
    content="SQL Injection Detection Playbook:\n"
            "1. Identify all user input entry points (query params, headers, body)\n"
            "2. Trace each input to database query construction\n"
            "3. Check for parameterized queries vs string concatenation\n"
            "4. Verify ORM usage doesn't bypass parameterization\n"
            "5. Check stored procedures for dynamic SQL",
    metadata={"type": "strategy_guide", "game_type": "sql_injection",
              "source": "security_team"}
)
```
Why KB: these are static reference documents. They don't change per game — they're the "textbook" the agent consults. Vector search finds relevant strategies for the current game type.

### Storage (Blob) — Large Artifacts
- Training JSONL datasets (can be MBs)
- Model checkpoints (can be GBs)
- Exported HuggingFace datasets

Why storage: these are large binary/text files that don't benefit from graph relationships or semantic search.

### Blockchain — Incentive Signal
- Reward tokens minted on game win (already implemented)
- Token balance = cumulative agent performance metric
- Future: agents "spend" tokens to access harder games or better compute

## Reward Shaping

Terminal reward from the game (1.0 win, -1.0 loss) is discounted back through the move sequence using gamma decay:

```
Game: 7 moves, agent wins (reward=1.0), gamma=0.95
Move 7 (terminal): reward = 1.0
Move 6: reward = 0.95
Move 5: reward = 0.9025
Move 4: reward = 0.857
Move 3: reward = 0.814
Move 2: reward = 0.774
Move 1: reward = 0.735
```

This teaches the model that early moves matter but terminal moves matter more. The eval score from Bedrock (0.0–1.0) multiplies the terminal reward, so well-played wins are worth more than sloppy wins.

## Convergence

Reuses `ConvergenceState` from `components/games/runtime/convergence.py`. After each training batch:
1. Play N evaluation games with the updated model
2. Record average eval score
3. Feed to convergence tracker
4. If `should_stop()` returns True → training complete
