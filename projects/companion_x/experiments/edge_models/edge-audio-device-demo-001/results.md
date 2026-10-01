# Results: edge-audio-device-demo-001

**Status:** Functional ARM64 Linux demonstration completed on 2026-09-30.
**Tracking:** [ENG-200](https://linear.app/ditto/issue/ENG-200)

The 1,043-parameter keyword model ran offline in a disposable ARM64
`edge-lab` container. It returned a `go`, `stop`, or `other` prediction for
each of twelve anonymous WAV clips from speakers held out of training. The
container did not receive the clips' labels or original source filenames.

| Check | Observation |
| --- | --- |
| Exported model | 10,918-byte NumPy `.npz`; 1,043 parameters |
| PyTorch parity | 12/12 decisions matched; maximum probability difference `3.144e-6` |
| Demo outcomes | 7/12 correct; confusion rows `go`, `stop`, `other`: `[[2,0,2],[0,3,1],[2,0,2]]` |
| Input-to-score latency | p50 `1.086 ms`, p95 `1.142 ms` over 360 repeats; staged WAV read, preprocessing, inference |
| Peak process RSS | 48,000 KiB, including Python and NumPy |
| Container | Linux aarch64, Python 3.12.14, NumPy 2.4.4, 1 CPU, 512 MiB memory, no network, read-only root |

The twelve clips were selected by a fixed hash, four per class, with distinct
test speakers. Their 7/12 accuracy is an illustration only. The earlier full
speaker-disjoint held-out test result for this model was macro F1 `0.722` on
1,277 clips, with 156 false `go`/`stop` triggers among 954 other spoken words.
The mini dataset has no silence or ambient-noise cohort. These findings do not
establish safe command execution, iPhone performance, or mesh behavior.

The [run index](run-index.json) pins the source, model, individual staged WAV,
and output hashes. Open the [playable local demo](results/arm64-demo.html) to
hear each clip and inspect the predictions. That HTML embeds audio and is
ignored by Git; raw audio and generated artifacts remain outside commits.

The final measured run used [`run_edge_lab.sh`](run_edge_lab.sh), which starts
a disposable workload with this Docker invocation and a unique name:

```sh
docker run -d --name edge-audio-demo-001 --platform linux/arm64 \
  --network none --cpus 1 --memory 512m --memory-swap 512m --read-only \
  --tmpfs /work:rw,exec,size=160m --tmpfs /tmp:rw,size=160m \
  python-factory/edge-lab:local
```

The payload and pinned NumPy wheel were streamed into `/work`; NumPy was
unpacked there without network access. After copying the predictions back,
the launcher's `EXIT` trap removed its own uniquely named container with
`docker rm -f "$container"`. The next gate is a real iPhone
export/runtime run and an ambient-noise and silence evaluation.
