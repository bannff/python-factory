# Results: edge-tool-routing-001

**Status:** Synthetic lab probe, 29 September 2026. **Decision:** Stop the
standalone MiniLM router; revise a guarded design on a new held-out cohort.
These 55 examples were authored for this probe and are not evidence of real
operator-request quality. The 25 development and 30 evaluation requests use
disjoint paraphrase families and cover four read-only capabilities plus
abstention.

| Candidate | Held-out tool accuracy | Positive tool and arguments exact | Out-of-scope abstention | Unsafe misroutes |
| --- | ---: | ---: | ---: | ---: |
| Keyword/rule router | 26/30 (86.7%) | 16/20 (80%) | 10/10 | 0/10 |
| MiniLM embedding-centroid router | 21/30 (70%) | 17/20 (85%) | 4/10 | 6/10 |
| MiniLM plus deterministic safety gate, **post-hoc** | 27/30 (90%) | 17/20 (85%) | 10/10 | 0/10 |

The downloaded `all-MiniLM-L6-v2` revision was used as a frozen encoder;
development examples formed class centroids, and the request's IDs were
parsed deterministically. The encoder therefore was adapted through its
decision layer, not fine-tuned. The standalone semantic route incorrectly
selected tools for requests to change a threshold, erase alerts, negate a
sync request, and push an update. Its 2.2 ms median request time was measured
on an Apple Silicon development host and says nothing about iPhone latency.

The safety gate was added **after inspecting the evaluation errors**. Its
improved score is exploratory and cannot be used as a confirmatory holdout
result. Neither router executed any tool or physical action.

## Limits and next gate

- Create a larger, human-reviewed request set with real operator language,
  explicit authorization labels, out-of-scope requests, and frozen templates
  that remain unseen during guard design.
- Evaluate exact typed arguments, abstention, and unsafe misroutes first.
  A semantic model may suggest a capability only behind deterministic schema,
  permission, negation, and multi-intent checks.
- Benchmark full tokenizer, encoder, and guard size and resources after iPhone
  export. Only then test typed request/result handoff over disconnected peers.
- FunctionGemma 270M is a separate candidate that still needs authorized
  weight access and its own frozen evaluation; it was not run here.

See the [run index](run-index.json) for source and artifact hashes once sealed.
