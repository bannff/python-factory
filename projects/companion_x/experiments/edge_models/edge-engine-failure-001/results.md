# Results: edge-engine-failure-001

**Status:** Exploratory lab pilot, 29 September 2026. **Decision:** Revise and
continue the logistic baseline as the quality comparator. No candidate is
promoted for on-device use. [ENG-173](https://linear.app/ditto/issue/ENG-173/edge-device-multi-model-family-experimentation)
holds the compact evidence bundle with code snapshots, manifests, endpoint
scores, Workflow SQLite journal, and artifact hashes.

| Candidate | Validation AUPRC | Validation recall / false positives | Official test AUPRC | Official test recall / false positives |
| --- | ---: | ---: | ---: | ---: |
| Logistic regression | 0.935 | 67% / 2 of 48 | 0.980 | 80% / 0 of 75 |
| LightGBM | 0.909 | 69% / 2 of 48 | 0.951 | 68% / 1 of 75 |
| TCN, three epochs | 0.901 | 62% / 2 of 48 | 0.943 | 56% / 0 of 75 |
| Calibrated LightGBM + TCN mean | 0.897 | 62% / 2 of 48 | 0.960 | 64% / 1 of 75 |

The two-model policy did not improve validation AUPRC versus the logistic
baseline. The paired bootstrap interval for the difference was −0.077 to
−0.006. The TCN result is a short training probe, not a settled family verdict.

Companion-X's ML MCP trained LightGBM and TCN. A separate durable Workflow
MCP run invoked both predictions sequentially. The retained SQLite journal
contains two succeeded runs and four succeeded named-tool attempts after a
rerun-key fix. The Workflow run used freshly trained models and returned
prediction artifacts; it did **not** execute the evaluated fusion policy.
There was no Ditto mesh or iPhone execution.

## Deviations and limits

- The official test set was viewed during the logistic pilot before candidate
  comparison ended. All official-test comparisons are exploratory.
- Validation recall and false-positive counts are selection estimates: the
  threshold was chosen on the same out-of-fold endpoints being summarized.
- FD001 is simulated. Its constructed validation RUL distribution need not
  match operational field data.
- The run code was outside this repository when executed. The evidence bundle
  includes later source snapshots and artifact hashes, but it does not prove
  exact runtime source identity for every run.
- No on-device latency, RAM, energy, thermal, export-parity, or mesh behavior
  was measured.

## Next gate

Freeze a fresh untouched evaluation cohort and training budget, then export
the strongest small candidates and benchmark on the selected iPhone. Advance
to two-device Ditto coordination only after a device result and a typed task/
result contract exist. Track each later run as a separate immutable evidence
record linked from [the run index](run-index.json).
