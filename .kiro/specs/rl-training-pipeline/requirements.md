# RL Training Pipeline — Requirements

## Context

Beads `python-factory-lczg` (RL Agent Economy Pipeline) and `python-factory-28su` (Game transcript to training data). The games brick generates structured game transcripts stored in Neo4j. The ML brick has fine-tuning capabilities (MLX QLoRA on Apple Silicon, Bedrock). The blockchain brick tracks agent rewards. The missing piece: closing the loop from game outcomes → training data → model updates → better game play.

## Data Flow

```
Agent plays game → GameSession + GameMove nodes in graph
                 → Blockchain reward tokens
                 → Evals rubric score (Bedrock)
                 → Convergence tracker
                         ↓
              Transcript extraction (graph → JSONL)
                         ↓
              ML brick fine-tuning (QLoRA/LoRA)
                         ↓
              Updated model weights
                         ↓
              Agent plays next game (with improved model)
```

## Requirements

### R1: Transcript Extraction
Extract game transcripts from Neo4j graph into JSONL training format. Each transcript becomes one or more training examples.

### R2: Training Data Format
Output JSONL compatible with the ML brick's `ml_dataset_create_pipeline`:
```jsonl
{"input": "<game state + legal moves>", "output": "<agent's move>", "reward": 0.7, "metadata": {"game_id": "...", "game_type": "sqli", "move_step": 3}}
```

### R3: Reward Shaping
Training examples are weighted by outcome:
- Winning game moves get positive reward (scaled by eval score)
- Losing game moves get negative reward
- Intermediate moves get discounted reward (gamma decay from terminal)

### R4: Data Storage Taxonomy
| Data Type | Where | Why |
|-----------|-------|-----|
| Active game state (board, moves) | Graph (GameSession entity) | Live CRUD, survives restarts |
| Finished game transcripts | Graph (GameSession + GameMove nodes) | Lineage, queryable relationships |
| Training JSONL datasets | Storage brick (blob) | Large files, versioned, exportable |
| Agent strategy memories | Memory brick | "I learned column 3 is strong opening" — semantic retrieval |
| Game rules / strategy docs | KB brick | "How to detect SQLi" — knowledge retrieval for agents |
| Eval scores per game | Graph (linked to GameSession) | Queryable, feeds convergence |
| Reward token balances | Blockchain (wallet entities) | Agent economy incentives |
| Model checkpoints | Storage brick (blob) | Large binary files |
| Convergence state | Memory brick | Per-agent training progress |

### R5: Pipeline Orchestration
The training pipeline is a workflow:
1. Query graph for finished games since last training run
2. Extract transcripts → JSONL
3. Filter by minimum eval score (don't train on bad games)
4. Create ML dataset pipeline
5. Run fine-tuning job (QLoRA)
6. Store checkpoint
7. Update convergence tracker
8. If not converged: loop

### R6: Memory Integration
After each training batch, store a memory summarizing what was learned:
```python
memory_store(
    content="Trained on 50 SQLi games. Win rate improved from 0.3 to 0.6. Key pattern: agents that trace dataflow before submitting findings score 2x higher.",
    user_id="kiro-agent",
    metadata={"type": "training_insight", "game_type": "sql_injection", "batch_id": "..."}
)
```

### R7: KB Integration
Game rules, strategy guides, and vulnerability patterns are KB documents:
```python
kb_ingest(
    content="SQL Injection Detection Strategy: 1. Identify user input entry points...",
    metadata={"type": "strategy_guide", "game_type": "sql_injection"}
)
```
Agents retrieve these during gameplay via `kb_search`.

### R8: Convergence Criteria
Use the existing `ConvergenceState` from the games brick. Training stops when:
- Win rate plateaus (patience=5, epsilon=0.02)
- Max iterations reached (default 50)
- Eval score exceeds threshold (0.8)
