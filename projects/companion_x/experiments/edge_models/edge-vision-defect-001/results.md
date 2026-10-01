# Results: edge-vision-defect-001

**Status:** Exploratory lab pilot, 29 September 2026. **Decision:** Revise.
The compact pretrained image backbone improves the observed precision/recall
curve and reduces false alerts at the fixed 0.5 threshold, but the 52-positive
cohort is too small to establish a reliable gain. No iPhone or Ditto mesh
result exists.

The [KolektorSDD](https://www.vicos.si/resources/kolektorsdd/) source has
399 images from 50 production items, including 52 defect-positive images.
Three official folds hold out whole items; the table combines out-of-fold
**image-level** predictions. Every item contains a defect somewhere, so this
dataset cannot support an item-level defective/not-defective decision.

| Candidate | Image average precision | AUROC | Defects found | False alerts on 347 negative images |
| --- | ---: | ---: | ---: | ---: |
| Grayscale image features + balanced logistic regression | 0.717 | 0.904 | 39/52 at threshold 0.5 | 30 |
| Frozen MobileNetV3 Small + balanced logistic head | 0.778 | 0.911 | 40/52 at threshold 0.5 | 8 |

The paired, item-resampled 95% interval for the average-precision difference
(MobileNet minus baseline) is −0.089 to +0.222. It includes zero. The
backbone was pretrained on ImageNet; the experiment trained a small head,
not the backbone. The model input uses three overlapping crops per image,
which adds work beyond a single model call and must be included in any
device benchmark.

## Limits and next gate

- The dataset is CC BY-NC-SA 4.0 and suitable here only for noncommercial
  research; product data rights require separate review.
- No Core ML export or iPhone prediction parity, p95 latency, peak RAM,
  energy, or thermal behavior was measured. The full three-crop pipeline
  needs those measurements.
- This is one manufacturing dataset, with only 52 positive images and no
  evidence of generalization to Ditto customers' cameras or defects.
- A future mesh run should exchange a typed, read-only defect observation
  with image and model provenance, rather than autonomously acting on it.

Acquire a licensed, item/site-disjoint holdout closer to the target use case,
then compare the frozen model and simpler baseline on the named iPhone. See
the [run index](run-index.json) for data and artifact hashes once sealed.
