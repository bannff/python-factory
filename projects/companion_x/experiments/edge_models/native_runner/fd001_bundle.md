# FD001 native debug fixture

This stages the frozen ENG-184 FD001 sensor model and three official test-endpoint
rows for iOS and Android debug runners. Engines 1 and 2 remain the N=2 Ditto
peer assignments. Engine 20 is a supplemental positive decision row for native
scorer parity only; it is not a third peer or an unbiased model quality test.
Staging checks the ENG-184
scenario, both source file and payload SHA-256 values, all 100 source rows, and
host prediction parity. It does not execute a native app or Ditto SDK sync.

Run:

```sh
python -m projects.companion_x.experiments.edge_models.native_runner.fd001_bundle \
  --model /path/to/model.json --cohort /path/to/cohort.json \
  --output /path/to/bundles
```
The input files can stay in an ignored host artifact directory. The output is
`<output>/<sha256(manifest.json)>/{manifest.json,model.json,samples.json,dataset.json}`.
`model.json` retains the exact source bytes. The bundle is immutable: a repeated
stage verifies an existing directory and rejects changed contents.

`manifest.json` has `schema_version:2`, `kind:"fd001-native-bundle"`,
`runtime:"fd001-native-linear"`, `feature_count:480`,
`peer_engine_ids:[1,2]`, `parity_sample_engine_ids:[1,2,20]`,
`samples_file_sha256`, `dataset_file_sha256`,
`dataset_id:"fd001-native-selected-001"`, and `source` with
`scenario_sha256`, `model_file_sha256`, `model_payload_sha256`,
`cohort_file_sha256`, and `cohort_payload_sha256`. The source cohort itself is
not copied. `samples.json` has `schema_version:1`,
`kind:"fd001-native-samples"`, `feature_count:480`, and sorted `rows`. Each row
has `sample_id` (`engine-001`, `engine-002`, or `engine-020`), `engine_id`, 480 finite `features`,
`reference_probability` computed on the host, and `reference_decision` (0 or 1).
`dataset.json` follows the existing native evidence verifier's dataset manifest
schema: dataset ID, split `test`, ordered sample IDs, and SHA-256 of each
canonical selected-row JSON object.
The native scorer should infer all three rows in dataset order. The native
result verifier requires inference trace IDs and both prediction arrays to
match that three-row dataset exactly. Only `peer_engine_ids` controls N=2
device assignment and Ditto observations. The positive parity row is a known
answer selected from the frozen cohort; it cannot establish generalization.

The native scorer for `fd001-native-linear` reads the existing model fields.
For each feature: cast the scaler mean to float32, subtract from the input,
cast the difference to float32, divide by scaler scale, then cast to float32.
Multiply by the coefficient and sum with the intercept in float64. Apply a
numerically stable sigmoid, then classify with `probability >= threshold`.
Compare native probabilities against the row references within the frozen
scenario's tolerance. The host uses Python `math.fsum`; a platform's ordinary
sum may differ slightly, so report the measured maximum error.

For a `NativeScenario`, set `runtime` to `fd001-native-linear`, `model_sha256`
to `manifest.source.model_file_sha256`, `dataset_id` to `manifest.dataset_id`,
and `dataset_sha256` to `manifest.dataset_file_sha256`. Provide `dataset.json`
as the native verifier's dataset evidence file. Native compatibility remains unproven until an
iOS or Android app loads the bundle and the controlled runner verifies its
native predictions and Ditto SDK trace.
