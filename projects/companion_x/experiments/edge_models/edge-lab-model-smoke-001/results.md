# Results: edge-lab-model-smoke-001

**Run:** `run-001`, 30 September 2026. **Functional gate: passed.**
The checked-in runner exported the frozen `edge-engine-failure-001` logistic
artifact and the 100 official FD001 test endpoints. Companion-X Sandbox
uploaded the runner, model JSON, and cohort JSON into the running `edge-lab`
container, executed 10,000 timed inferences, and downloaded the result.
Host and container SHA-256 digests matched for the final runner, inputs, and
result. The final result retains all 100 per-engine predictions and errors.
The [run index](run-index.json) links the complete local evidence manifest,
execution log with exact commands and exit codes, and their hashes.

| Measure | Result |
| --- | ---: |
| Frozen endpoint scores finite | 100/100 |
| Warning decisions matching scikit-learn | 100/100 |
| Maximum absolute probability error | `3.33e-16` (gate `<=1e-6`) |
| Timed inferences | 10,000 (100 passes × 100 endpoints) |
| Scorer latency p50 / p95 | 96.834 / 111.833 µs |
| Whole Sandbox command | 1,123 ms |
| Process peak RSS | 21,078,016 bytes |
| Container cgroup memory, before / after | 12,599,296 / 13,094,912 bytes |
| Container cgroup peak to date | 18,141,184 bytes |

The first attempt failed the probability gate: collapsing the scaler into
float64 coefficients produced a maximum difference of `0.00030845`, although
all 100 decisions agreed. Inspection showed that scikit-learn's scaler casts
its means and scales to float32 and rounds after both subtraction and
division. The second attempt reproduced those steps and passed the gate; its
result kept only aggregates. The third attempt retained the 100 prediction
records and passed the same gate. All three attempts' raw results and inputs
are retained in the run manifest. The first runner source snapshot and full
original MCP response envelopes were not retained; the execution log was
assembled from this task's tool-call arguments and responses after the review.
Treat the first attempt as diagnostic evidence only.

**Decision: pursue** the Ditto local-write and two-peer experiments. This run
establishes functional parity for a small sensor model in one Linux container
and shows its Python scoring cost on this Docker Desktop host. It does not
measure iPhone memory, energy, thermal behavior, Core ML parity, Ditto local
persistence, or mesh delivery. The container has no configured memory limit.
The 100-endpoint cohort reuses the frozen dataset from the earlier FD001
record; this run did not create a new Dataset brick job. An authorized offline
Ditto license is still needed for the SDK persistence gate.
