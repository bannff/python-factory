# Protocol: edge-audio-command-001

**Question:** Can a small local audio model distinguish explicit `go` and
`stop` commands from other spoken words without network access? This is a
bounded command-recognition proxy; it is not authorization to execute physical
commands.

Use Google's [mini Speech Commands dataset](https://www.tensorflow.org/tutorials/audio/simple_audio):
8,000 one-second-or-shorter clips across eight words. Hash the original ZIP.
Derive the speaker group from the filename convention and freeze disjoint
train/validation/test speaker groups before fitting. Validate sample rates,
channels, duration, labels, and file hashes. This mini set lacks a dedicated
silence/background-noise cohort, so do not claim false-trigger performance in
ambient sound.

Compare a small convolutional keyword model against a simple audio-feature
classifier. Report held-out `go` and `stop` recall separately, false triggers
among the six other words, confusion counts, macro F1, class balance, model
parameter count and serialized bytes. Pick thresholds using validation only.
Record all feature preprocessing and its fitted state.

Publish the audio record definition and each frozen partition with the Dataset
brick after external schema and speaker-leakage checks. Later gates are export
parity and iPhone latency/RAM/energy, followed by a typed, read-only command
proposal through disconnected Ditto peers with explicit authority checks.

## Reproduce the lab run

Place the official `mini_speech_commands.zip` next to [the frozen runner](run.py)
and verify its SHA-256 against the [run index](run-index.json). Run
`python run.py` in an environment with NumPy, SciPy, scikit-learn, joblib,
and PyTorch. The runner creates a speaker-disjoint `split.tsv`, a baseline
model, the tiny CNN checkpoint, and `results.json` in this directory. It
selects the CNN epoch using validation macro F1 and evaluates the test
partition once. Raw audio and generated artifacts remain ignored by Git.
