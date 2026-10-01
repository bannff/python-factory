# Protocol: edge-audio-device-demo-001

**Tracking:** [ENG-200](https://linear.app/ditto/issue/ENG-200)

## Question

Can the frozen 1,043-parameter `edge-audio-command-001` model take a local WAV
on an offline ARM64 Linux `edge-lab` workload and return a `go`, `stop`, or
`other` proposal with decisions and probabilities that agree with the
training-host PyTorch model?

This experiment demonstrates local inference. It does not execute commands,
use Ditto, or measure an iPhone.

## Frozen inputs and separation

- Source: Google's [mini Speech Commands tutorial dataset](https://www.tensorflow.org/tutorials/audio/simple_audio),
  8,000 clips; tutorial describes the dataset as CC BY.
- Use the archive, speaker-disjoint `split.tsv`, training source, and trained
  checkpoint hashes pinned in [`prepare.py`](prepare.py). Reject any mismatch.
- Select four clips per class from the frozen test split using a fixed SHA-256
  order. Require distinct speakers. `other` covers the six remaining spoken
  words, not silence or ambient noise.
- Stage only anonymous `clip-NNN.wav` files, a label-free cohort index, and
  the exported NumPy weights to the container. Keep source filenames, words,
  speakers, and PyTorch reference scores host-side until after inference.
  Preparation requires a fresh output directory; the container launcher checks
  the exact payload file set and clip hashes before staging it.
- Export the frozen PyTorch state and normalization into a NumPy `.npz`. The
  device runtime uses Python standard library plus NumPy; it does not import
  PyTorch, SciPy, scikit-learn, or the factory on the device.

## Execution and checks

Run a disposable `linux/arm64` `edge-lab` container with no network, one CPU,
512 MiB RAM, a read-only root, and executable temporary work storage. Stage a
pinned ARM64 NumPy wheel offline. [`runtime.py`](runtime.py) reads each WAV,
computes the training-equivalent log-mel representation, and performs the
convolutions, batch normalization, pooling, and softmax. It rejects unexpected
sample format, length, clip path, or content hash.

Record each prediction and 30 repeated latencies per clip, timed from staged
WAV file read through score. Exclude one-time model loading. Compare all
decisions to the PyTorch reference and require a maximum per-class probability
difference at or below 0.001. Report p50 and p95 latency, peak process RSS,
model export size, and the container limits. The twelve-clip demo is a
functional probe; the full prior speaker-disjoint test split remains the
generalization result.

Generate a standalone HTML file with playable clips, three-class score bars,
predictions, and truth joined after inference. Do not expose original speaker
IDs or source filenames in the HTML.

## Reproduce

On the host, with NumPy and PyTorch available, run [`prepare.py`](prepare.py)
with `--archive`, `--split`, `--checkpoint`, and `--output`. Download a pinned
CPython 3.12 aarch64 NumPy 2.4.4 wheel and verify SHA-256
`f9e75681b59ddaa5e659898085ae0eaea229d054f2ac0c7e563a62205a700121`.
Build `python-factory/edge-lab:local` from the existing `edge-lab` Dockerfile,
then run [`run_edge_lab.sh`](run_edge_lab.sh) with the generated `payload`
directory, wheel, and output JSON path. Run [`render.py`](render.py) with the
predictions, host-side `truth.json`, `reference.json`, staged `clips` folder,
and desired HTML output path. No source dataset or credential is baked into
the image.
