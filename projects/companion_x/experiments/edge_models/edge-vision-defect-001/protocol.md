# Protocol: edge-vision-defect-001

**Question:** Can a phone-class image model flag a visible industrial surface
defect from a local camera image, with useful recall at a bounded false-alert
rate? This is a lab proxy for asset inspection, not a field acceptance result.

Use the [Kolektor Surface-Defect Dataset](https://www.vicos.si/resources/kolektorsdd/)
and its published three folds. The source contains 399 images, including 52
defect-positive images. Preserve original file identities, labels, official
fold membership, source archive digest, and license. The dataset is
**CC BY-NC-SA 4.0**; this research result does not grant product-data rights.
Inspect whether its official folds prevent physical-item overlap and disclose
any uncertainty. Do not random-split cropped images from the same item.

Compare a pretrained MobileNetV3-Small frozen backbone with a small trained
head against a simple hand-crafted image-feature classifier. Fit all
preprocessing and any threshold on training/validation portions only. Report
held-out AUPRC, defect recall, false positives/count, class balance, artifact
size, uncertainty where the tiny positive cohort allows, and source/model
hashes. An internal training metric is diagnostic, not headline evidence.

Record the image-specific JSONL fields in a versioned definition and
materialize immutable split artifacts through the Dataset brick. Validate
image decodability, dimensions, labels, file hashes, and item/fold isolation
externally because generic Dataset materialization does not enforce those
rules.

Later gates: verify converted-model prediction parity, p50/p95 inference
latency, RAM, energy, and thermal behavior on the specified iPhone; then
persist typed image-classification observations in the local Ditto SDK store
and verify subscribed peers receive them after offline/rejoin.

## Reproduce the lab run

Place the official `KolektorSDD.zip` and `KolektorSDD-training-splits.zip`,
plus the pinned MobileNetV3 Small weight file, under `sources/` next to
[the frozen runner](run.py). Their SHA-256 values are in the
[run index](run-index.json). Use PyTorch, TorchVision 0.28.0, Pillow,
NumPy, scikit-learn, and joblib, then run `python run.py`. The runner
materializes the official item-disjoint folds, out-of-fold scores, final
all-data heads for later export work, and a manifest. Raw images, source
archives, pretrained weights, and generated artifacts remain ignored by Git.
