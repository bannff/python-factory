# Results: edge-audio-command-001

**Status:** Exploratory lab pilot, 29 September 2026. **Decision:** Revise.
The tiny keyword model improves on the feature baseline, but false triggers
among other spoken words are too frequent to promote a command capability.
No iPhone or Ditto mesh result exists.

The source is Google's 8,000-clip mini Speech Commands dataset. The pilot
frozen split contains 5,615 training clips, 1,108 validation clips, and 1,277
test clips, with 1,221, 260, and 269 distinct speakers respectively. A hash
of speaker identity determined the partition before training. Both models
used the same `go`/`stop`/`other` labels, where `other` comprises six spoken
words; it contains no silence or ambient-noise examples.

| Candidate | Held-out macro F1 | Balanced accuracy | `go` recall | `stop` recall | Other words routed to a command |
| --- | ---: | ---: | ---: | ---: | ---: |
| MFCC + balanced logistic regression | 0.584 | 0.713 | 108/152 (71.1%) | 141/171 (82.5%) | 378/954 (39.6%) |
| 1,043-parameter depthwise CNN | 0.722 | 0.745 | 99/152 (65.1%) | 128/171 (74.9%) | 156/954 (16.4%) |

The CNN selected its checkpoint using validation macro F1 across 12 training
epochs. Its serialized weights are 13,429 bytes. That figure excludes audio
preprocessing, runtime, and memory use. The simpler model remains a useful
size and accuracy comparator; the CNN's lower `go` and `stop` recall also
matters despite its higher macro F1.

## Limits and next gate

- This is one small speaker-disjoint test cohort, not a field voice-command
  dataset. Silence, noise, far-field microphones, accents, and speaker drift
  were not evaluated.
- No Core ML export or iPhone prediction parity, p95 latency, peak RAM,
  energy, or thermal behavior was measured.
- No command was executed. A future mesh pilot should exchange typed,
  read-only command proposals, with authority and duplicate checks outside
  the classifier.

Add a silence/noise and real device-microphone cohort before judging
false-trigger fitness. Then freeze the operating threshold on validation,
export the model and preprocessing, and benchmark the complete pipeline on
the selected iPhone. See the [run index](run-index.json) for source and
artifact hashes once sealed.
