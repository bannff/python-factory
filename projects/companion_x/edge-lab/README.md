# edge-lab

`edge-lab` is a single Linux container for rehearsing the
`edge-ditto-device-flow-001` experiment. Its image contains Python 3.12 and a
hash-locked Ditto Python SDK preview wheel. It contains no license, model,
dataset, or experiment results.

Build from this directory:

```sh
docker build -t python-factory/edge-lab:local .
```

Set `SANDBOX_ADAPTER=docker` and point `SANDBOX_PROFILES_DIR` at the absolute
`projects/companion_x/sandbox-profiles` directory in the MCP server's
environment. Until this branch's Sandbox code is installed in the server's
Python environment, also put this worktree's `components/sandbox/src` first
on `PYTHONPATH` so the `replace_existing: false` profile field is recognized.
Restart that server, then call
`sandbox.provision(profile="edge-lab")`. The profile keeps the container
running for `sandbox.upload_file` and `sandbox.execute`; call
`sandbox.terminate(env_id=...)` when finished. A second provision refuses to
replace an existing `edge-lab` container. The Sandbox runtime currently
keeps its environment registry in memory, so restart the MCP server only
after terminating the container or recover it by Docker name.

The existing Sandbox profile registry is the source of device configuration.
This profile requests a Linux ARM64 container and records `iphone` as the
intended device family with `linux_proxy` fidelity. The generic profile fields
`cpus` and `memory_mb` can apply a resource envelope once a specific device
model and limits are chosen. The profile does not turn Docker into iOS or
reproduce Apple silicon, the Neural Engine, radios, energy use, or thermal
behavior. Reprovision after changing the YAML; an already running container
keeps its original Docker settings. Use `docker inspect` to record the actual
image, platform, CPU quota, and memory limit in each experiment's evidence.

These instructions target the Companion-X MCP server running directly on the
host. The separate Companion-X Compose security overlay selects LocalStack
and does not mount this profile directory; it does not use this setup.

The experiment runner will launch N independent processes inside this
container. Each process must open its own SDK instance, persistence directory,
and loopback TCP port; the processes share one test database ID. Supply the
authorized offline Ditto license at run time through a protected local input.
Do not put it in this profile, Dockerfile, command history, or checked-in
artifacts. Model and dataset artifacts are uploaded for a run and identified
by hash in its manifest. The run output belongs in artifact storage, with
curated evidence linked from the experiment's `run-index.json`.

This setup can assess local writes, persistence, and TCP peer sync on Linux.
It cannot establish iPhone resource behavior or independent device network
conditions. Those are separate experiment stages.
