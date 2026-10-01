# ENG-202 sealed N=2 SDK preflight

**Decision, 2026-09-30:** Proceed to a licensed two-peer rehearsal only after the protected offline-license mount, current-code Companion-X MCP process, and host cleanup job are verified. The license-free image preflight passed. No Ditto SDK peer process, local write, reopen, replay, or sync ran in this step.

## Frozen inputs and build

- Scenario: `scenario-n2.json` schema v2; FD001 scaled logistic model and official test endpoint cohort, with engine IDs 1 and 2 selected for the later N=2 run.
- Reviewed source, model, cohort, entrypoint, and installed `dittolive-ditto` distribution digests are pinned in `sealed_pins.json`. The generated host evidence records all staged context hashes.
- Linux ARM64 final image: `sha256:040c91591c28154252bf921759cbbf5255a555f739e0d2484c837bc975c12eed`. The generated `edge-n2-sdk` profile pins that ID, one CPU, 512 MiB, an internal-only peer network, a symbolic offline-license secret reference, and a fixed `run` command.
- Build and preflight Docker networks were `none`; no license was mounted. The preflight checked 100 model/cohort parity rows and the installed SDK digest, then reported `license_used=false` and `peers_launched=false`.

Host-local evidence: `work/edge_ditto_sealed_image_001/build-003/build-evidence.json` relative to this task workspace. The generated profile and build evidence remain ignored by Git; their hashes are in that evidence record. An independent reviewer found no material defect in the sealed runner, collector, metrics, or local-tag build fix. A separate host image inspection confirmed the recorded image ID, `linux/arm64` platform, and fixed Python entrypoint.

## Verification and limits

### Disposable iPhone-envelope proxy probe

On 2026-09-30 a fresh Companion-X MCP process listed the `edge-lab` profile and the `iphone-15` **Linux proxy** preset, then provisioned `edge-lab-9071ef8b4394` with `device_preset=iphone-15`, `timeout_seconds=600`, and automatic termination. Docker inspection identified a new container `1f1bff34abdc1c8beee029aee44f3e15b682bea437ac75c6ed570fc72329f7ec` using image `sha256:ea55631109384789e3dbe2b5d36cfd9aa3d83e32d4b98d6fc19e60b853c21348`, `linux/arm64`, two CPUs (`NanoCpus=2000000000`), 2 GiB RAM (`Memory=2147483648`), and no published ports. The existing generic `edge-lab` container remained running under its original ID. The worker terminated only the fresh environment and confirmed it was gone. This verifies Sandbox provision/limit/cleanup behavior for the declared proxy envelope; it does not emulate iOS or prove an SDK peer run.

The peer harness, stopped-container collector, and sealed-image tests passed locally (52 tests and 23 subtests, including the post-build base-tag drift regression). The collector is designed to retain validated failed-run evidence and reject altered predictions, unowned containers, unexpected ports, missing hashes, and performance claims that do not meet the declared gates. These are contract checks, not a live licensed SDK result.

The N=2 scenario has only two selected observations. Its declared p95 gate requires at least 20 samples per latency metric, so even a functional two-peer pass will not close ENG-184's performance acceptance. The end-to-end metric includes deliberate reopen, replay, startup, and convergence; it is a rehearsal-cycle measurement, not steady-state phone latency. No iOS runtime, device radio, power, or thermal claim is supported.

Open prerequisites: the authorized offline-license file path is not configured, and the reviewed host sweeper LaunchAgent is not installed. Companion-X MCP instances diverge: the fresh worker process provisioned with current profiles, while this parent session still lists only six old built-ins after capability reload. The licensed sealed profile must be run through a verified current-code process. [ENG-184](https://linear.app/ditto/issue/ENG-184/run-first-offline-ditto-sdk-edge-inference-to-observation-gate) remains In Progress. [ENG-203](https://linear.app/ditto/issue/ENG-203/schedule-safe-cleanup-for-secret-enabled-sdk-containers) tracks host cleanup activation.
