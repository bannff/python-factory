# Protocol: edge-maintenance-dispatch-demo-001

**Question:** Can a tiny trained model turn 100 sensor windows into an
auditable, offline maintenance work queue under a phone-class container
budget, with two logical cell agents sharing dispatch capacity?

## Business flow

The frozen FD001 logistic scorer evaluates each engine endpoint. Two logical
cell agents own alternating assets, while a deterministic shift coordinator
uses only model probabilities to rank predicted risks. It proposes two
immediate technician dispatches, one next-shift review, backlog items for
remaining alerts, and monitoring for the rest. Every proposed work order
requires human approval. RUL labels are used only after routing to summarize
the holdout recall; they never influence an action.

The cross-device event/session is a synthetic composition over NASA simulated
engine endpoints. This demo has no aligned audio/vision/sensor field dataset,
no Ditto SDK persistence or peer synchronization, and no native phone-runtime
claim. Its local SQLite journal demonstrates stable task identity and replay
inside one container only.

## Frozen inputs and gates

- Use `edge-lab-model-smoke-001`'s already trained JSON export and frozen 100
  official FD001 endpoints. Do not retrain or adjust the threshold.
- Run the existing scorer in `edge-lab` and require its functional parity gate
  (100/100 decision agreement and maximum probability error at most `1e-6`).
- Run `dispatch_demo.py` against that exact model, cohort, and result. Require
  100 unique asset predictions, verified provenance, a persisted session, and
  100 stable task rows after running twice.
- Preserve a digest of the exact script, model, cohort, raw inference result,
  local session database, and sanitized dispatch summary.

## Container run

Create `/tmp/edge-maintenance-dispatch-demo-001` in the already running
`edge-lab` container, then stage these files with Docker copy: the existing
`edge-lab-model-smoke-001/run.py`, `model.json`, `cohort.json`, and this demo's
`dispatch_demo.py`. The model and cohort live in the ignored experiment run
directory; the runner and dispatcher are tracked source.

```sh
docker exec edge-lab mkdir -p /tmp/edge-maintenance-dispatch-demo-001
docker cp <repo>/projects/companion_x/experiments/edge_models/edge-lab-model-smoke-001/run.py edge-lab:/tmp/edge-maintenance-dispatch-demo-001/run.py
docker cp <repo-work-runs>/edge-lab-model-smoke-001/run-001/model.json edge-lab:/tmp/edge-maintenance-dispatch-demo-001/model.json
docker cp <repo-work-runs>/edge-lab-model-smoke-001/run-001/cohort.json edge-lab:/tmp/edge-maintenance-dispatch-demo-001/cohort.json
docker cp <repo>/projects/companion_x/experiments/edge_models/edge-maintenance-dispatch-demo-001/dispatch_demo.py edge-lab:/tmp/edge-maintenance-dispatch-demo-001/dispatch_demo.py
docker exec edge-lab python /tmp/edge-maintenance-dispatch-demo-001/run.py infer --model /tmp/edge-maintenance-dispatch-demo-001/model.json --cohort /tmp/edge-maintenance-dispatch-demo-001/cohort.json --output /tmp/edge-maintenance-dispatch-demo-001/inference.json --repeats 10
docker exec edge-lab python /tmp/edge-maintenance-dispatch-demo-001/dispatch_demo.py --model /tmp/edge-maintenance-dispatch-demo-001/model.json --cohort /tmp/edge-maintenance-dispatch-demo-001/cohort.json --result /tmp/edge-maintenance-dispatch-demo-001/inference.json --state-db /tmp/edge-maintenance-dispatch-demo-001/session.db --output /tmp/edge-maintenance-dispatch-demo-001/dispatch-summary.json
```

Run the final command a second time to demonstrate replay idempotency. Capture
stdout and copy the machine-readable result files into the host-side `work/runs`
record for the run manifest. The container `/tmp` directory is disposable.
