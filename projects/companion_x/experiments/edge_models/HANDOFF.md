# Edge model experiments — handoff

**Updated:** 2026-10-01 (America/Los_Angeles)
**Working checkout:** `/Users/danielrodrigo/Documents/Codex/2026-09-29/onbo/work/python-factory-edge-model-catalog`
**Branch:** `chore/python-factory-edge-model-catalog`
**Remote state:** PR [#88](https://github.com/bannff/python-factory/pull/88) is open; merge is pending required checks. See Linear ENG-173 for current tracking.

## Current program state

The parent tracker is [ENG-173](https://linear.app/ditto/issue/ENG-173/edge-device-multi-model-family-experimentation). The implementation spans Sandbox, Dataset, Evals, and Companion-X experiments. Preserve this checkout when continuing; it contains work accumulated over prior iterations.

| Issue | State | Verified status |
| --- | --- | --- |
| ENG-181 | Done | Polymorphic phone/tablet/Linux proxy presets and Sandbox contracts/tests are implemented. Presets explicitly identify `linux_proxy`; they do not claim native iOS or Android emulation. |
| ENG-187 | Done | Dataset edge-window/routing contracts and Evals evidence contracts are implemented. Focused Dataset edge suite: 164 passed; Evals edge evidence suite: 11 passed. |
| ENG-197 | Done | Live Sandbox-owned peer network test resolved a peer alias and delivered TCP payload between two isolated ARM64 containers; both temporary containers/network were removed. This was TCP transport only, not Ditto sync. |
| ENG-184 | In Progress | Sealed N=2 Ditto SDK runner and image preflight exist. SDK package is present in `edge-lab`; no real SDK peer write/reopen/replay/sync has run. The current Companion-X MCP now lists `edge-n2-sdk`, but only `edge-lab` is running. The N=2 profile requires the named protected secret `ditto-offline-license`. |
| ENG-185 | In Progress | Native result contracts, preflight, and integrity verifier exist; no native app/controlled runner is present in this checkout. Current host preflight is blocked: Xcode is not selected, and `simctl` is unavailable. No iOS app ran. |
| ENG-186 | In Progress | Native result contracts, preflight, and integrity verifier exist; no native app/controlled runner is present in this checkout. Current host preflight is blocked: Android SDK/`ANDROID_SDK_ROOT`, Java, `adb`, and `emulator` are unavailable. No Android app ran. |
| ENG-188 | In Progress | Typed mesh records and deterministic local reducer/fault corpus exist. Current evidence is a synthetic logical-peer baseline; no heterogeneous model pair has coordinated over real Ditto SDK sync. It remains gated on ENG-184. |

## Immediate gates and safe next actions

1. **ENG-184 / offline license:** Sandbox resolves `ditto-offline-license` through the Companion-X MCP server environment variable `SANDBOX_SECRET_DITTO_OFFLINE_LICENSE_FILE`. Configure it to an authorized protected regular file path on the MCP host; never put token bytes in a command, repository file, profile, or Linear/Notion update. An employee license source does not establish that this machine has a token configured. After configuration, verify the profile preflight, run the sealed N=2 scenario, collect only sanitized evidence with `collect_sealed.py`, and remove the test container through the collector/cleanup path.
2. **ENG-185:** Install/select full Xcode and a supported iOS Simulator runtime, then add/run the actual Swift app fixture and Ditto SDK persistence/reopen/peer test. The current probe output is preflight-only.
3. **ENG-186:** Install/configure Android SDK, platform tools, emulator image, Java, and license acceptance; then add/run the actual Kotlin app fixture and Ditto SDK persistence/reopen/peer test. The current probe output is preflight-only.
4. **ENG-188:** After ENG-184 passes, run the frozen N=2 heterogeneous audio/vision or sensor/vision task over Ditto, then N=4 fault cases. Compare against the existing local deterministic baseline and record quality, unsafe routes, completion/failover, p95 latency, database growth, mesh bytes, and per-device resource costs.

The host probes run on 2026-10-01 against planning-only scenarios. iOS reported `xcodebuild` requires a full Xcode developer directory and `xcrun` cannot find `simctl`. Android reported unset SDK roots, no Java runtime, and missing `adb`/`emulator`. Neither probe builds or launches an app.

## Artifacts and evidence boundaries

- Experiment catalog and demos: `projects/companion_x/experiments/edge_models/`.
- N=2 SDK protocol and sealed runner: `edge-ditto-device-flow-001/`.
- Native contracts/preflight/verifier: `native_runner/`.
- No checked-in iOS/Android `NativeScenario` JSON manifests exist yet; today’s host probes used transient planning values and do not attest simulator/AVD inventory.
- The frozen source artifacts currently exist outside Git at `/Users/danielrodrigo/Documents/Codex/2026-09-29/onbo/work/runs/edge-lab-model-smoke-001/run-001/{model.json,cohort.json}`. Their pinned file digests are model `58128c57716e9643ba18922b2281511c29722df4d4871ed264cf4037eb5755fe` and cohort `5cae03aa99132cbaa646f8e78187414649972c3635d268b49843e8f9f6438fbf`. The staged native dataset manifest for selected engines 1, 2, and 20 hashes to `8a3e1e04ce0ae767f75717ae42740c2cd876d705a6ee08cf7cbb001cc84d1c72`. These files are machine-local; another checkout needs the source artifacts before it can restage the bundle.
- `edge-mesh-coordinator-001/results.md` describes a synthetic reducer run, not real model-to-model Ditto mesh interop.
- The running `edge-lab` container is a Linux ARM64 proxy. It is not an iPhone runtime. Only the existing `edge-lab` sandbox was listed as running at handoff time; `edge-n2-sdk` was available as a profile but not provisioned.
- Prior focused verification recorded in the active issues includes Sandbox device/peer tests (130 passed), UDS mounts (32 passed with local socket permission), and the combined Companion-X edge/native suite (485 passed, 25 subtests). A broader Dataset run recorded 660 passed, 54 skipped, and 11 unrelated CAN terminal failures due to missing `cantools`.

## Tracking

Keep Linear as the source of experiment status and progress: update ENG-173 and the relevant child issue with evidence, blockers, next step, and ETA. The Notion AI Engineering Atlas is company guidance, not a project handoff or experiment log. This work is tracked in Linear ENG issues; no GitHub issue is the active tracker. Do not close an issue until its acceptance criteria have evidence from the target runtime, not just contracts or mocked preflight tests.
