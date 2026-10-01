# Results: edge-maintenance-dispatch-demo-001

**Run:** `run-001`, 30 September 2026. **Container functional gate: passed.**

The frozen trained logistic model scored all 100 official FD001 endpoint
windows in `edge-lab`; maximum probability error was `3.33e-16`, all 100
threshold decisions matched the saved scikit-learn reference, and p95
single-inference latency was `112.25 µs` for this 1,000-inference run. The
deterministic shift policy proposed two technician dispatches, one next-shift
review, and queued the remaining 17 alerts for planning. The model predicted
20 alerts; recall against the evaluation-only RUL labels was 20/25 (80%). No
label influenced dispatch selection.

The two logical cell agents own alternating assets. The replay created one
session and 100 stable tasks; the second run left the same one session and 100
tasks, and the dispatch JSON hash was identical. The planner output is
human-approved; the demo did not actuate equipment. The [run index](run-index.json)
links the sanitized summary and ignored host-side evidence manifest.

This demonstrates an on-container model-to-business-workflow path, not a
multi-family model ensemble: only the trained sensor model runs inference;
the coordinator is deterministic. The two logical workers are not Ditto
peers, the SQLite journal is not the Ditto SDK database, and NASA engine
simulation is not field equipment data. The FD001 test set has been viewed in
prior exploratory work, so quality numbers remain exploratory. Audio/vision
outputs are not synchronized with these sensor events. All actions are
proposals for a human planner.

**Decision:** Pursue the next experiment: run the same typed task/result flow
over licensed Ditto SDK peers, then add an aligned multimodal event cohort.
This run is not evidence for phone compatibility, offline mesh behavior,
model generalization, or a trained multimodal coordinator.
