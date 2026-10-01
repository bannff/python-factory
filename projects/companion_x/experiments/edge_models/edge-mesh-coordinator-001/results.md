# ENG-201 frozen local fault-corpus comparison

Corpus SHA-256: `d910bbdebfe5dc05c2badda50e0d787f922420453f00f629f4157e584618a189`. Seed: `20260930`. Policy: `policy-v1` (SHA-256 `3ff8a7658580aea0dd47ccf3f6ac2da7cee7c637d8766415d6af0875372893d2`). 24 synthetic scenarios.

20 scenarios are development regression fixtures revised during preflight. 4 are declared held-out policy checks with different templates/topologies. Artifact hashes prove byte consistency of the final bundle, not an independently timestamped untouched evaluation sequence or generalization to field data.

**Scope:** Model-independent, in-process logical peer records only. No Ditto SDK, transport, model inference, native app, or device emulation ran. Claims are proposals; no external action was executed.

Every Result row was seeded into the input before reduction. The comparison counts accepted synthetic Result rows under two visibility policies; it does not demonstrate improved real task completion or model quality.

| Metric | Local only | Deterministic coordinator |
| --- | ---: | ---: |
| Cases with an accepted seeded Result row | 2 | 16 |
| Abstained cases | 22 | 4 |

Integrity failures closed: 1; unsafe routes: 0; accepted stale claims: 0; duplicate accepted Result rows: 0; competing completed-Result proposals: 1. Replay: 47216 permutations, 0 mismatches. Logical peer-loss/rejoin cases with accepted seeded Results: 2/2; later-revision reclaim: 1/1. Claims issued while absent then recorded after rejoin rejected: 1.

Held-out cases: 4; accepted seeded Results: 2.

| Case | Split | Logical peers | Local only | Coordinator | Selected peer | Replay | p50 / p95 ms | State bytes |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| local-eligible | development | 1 | completed | completed | local-eligible-p0 | 5040 | 0.2051 / 0.2216 | 1374 |
| remote-eligible | development | 2 | abstained | completed | remote-eligible-p1 | 5040 | 0.2094 / 0.2365 | 1383 |
| stale-capability | development | 2 | abstained | abstained | — | 720 | 0.1422 / 0.1650 | 1189 |
| duplicate-delivery | development | 2 | abstained | completed | duplicate-delivery-p1 | 32 | 0.2639 / 0.2895 | 1410 |
| claim-race | development | 2 | completed | completed | claim-race-p0 | 32 | 0.2990 / 0.3322 | 1569 |
| expired-claim | development | 2 | abstained | abstained | — | 5040 | 0.1722 / 0.1922 | 1337 |
| peer-loss | development | 4 | abstained | completed | peer-loss-p2 | 32 | 0.2720 / 0.2960 | 1647 |
| peer-rejoin | development | 4 | abstained | completed | peer-rejoin-p2 | 32 | 0.3571 / 0.3797 | 1743 |
| cross-session | development | 4 | abstained | active | cross-session-p1 | 5040 | 0.1671 / 0.1753 | 1344 |
| same-id-conflict | development | 4 | abstained | integrity_error | — | 5040 | 0.0584 / 0.0611 | — |
| post-expiry-replay | development | 2 | abstained | completed | post-expiry-replay-p1 | 5040 | 0.1989 / 0.2150 | 1410 |
| reclaim-after-expiry | development | 4 | abstained | completed | reclaim-after-expiry-p2 | 32 | 0.2731 / 0.2932 | 1765 |
| capability-unavailable-transition | development | 4 | abstained | completed | capability-unavailable-transition-p2 | 32 | 0.3172 / 0.3463 | 1917 |
| claim-withdrawal-transition | development | 4 | abstained | completed | claim-withdrawal-transition-p2 | 32 | 0.2736 / 0.2982 | 1833 |
| late-completion-revision-race | development | 4 | abstained | completed | late-completion-revision-race-p1 | 32 | 0.3215 / 0.3448 | 2073 |
| membership-interrupted-rejoin | development | 4 | abstained | completed | membership-interrupted-rejoin-p1 | 32 | 0.3053 / 0.3400 | 1879 |
| delayed-result-recording | development | 2 | abstained | completed | delayed-result-recording-p1 | 5040 | 0.2011 / 0.2154 | 1464 |
| delayed-claim-recording | development | 2 | abstained | completed | delayed-claim-recording-p1 | 5040 | 0.2166 / 0.2264 | 1455 |
| result-before-claim-persistence | development | 2 | abstained | active | result-before-claim-persistence-p1 | 5040 | 0.1728 / 0.1830 | 1507 |
| claim-issued-while-absent | development | 2 | abstained | abstained | — | 32 | 0.1936 / 0.2139 | 1579 |
| unavailable-remote | held-out | 2 | abstained | abstained | — | 720 | 0.1389 / 0.1475 | 1203 |
| result-owner-mismatch | held-out | 2 | abstained | active | result-owner-mismatch-p1 | 32 | 0.2092 / 0.2316 | 1488 |
| three-way-race | held-out | 4 | abstained | completed | three-way-race-p1 | 32 | 0.4045 / 0.4359 | 1852 |
| lost-peer-historical-completion | held-out | 4 | abstained | completed | lost-peer-historical-completion-p1 | 32 | 0.2239 / 0.2440 | 1602 |

Process timing measures Python record parsing, reduction, and state serialization on this host; it is not device or mesh latency. Canonical state bytes measure serialized reducer output, not Ditto payload traffic or store growth. Multiple completed-Result proposals may have been authored for one task; this run cannot tell whether one or multiple workers performed work. No external actions were run. The local policy requires a Claim record timestamp no later than a Result's claimed completion; it does not prove the record was durable on a device. Event times can be backdated in unsigned records; trusted clock or signature provenance remains unmeasured.

Unavailable: mesh_bytes, database_growth, radio_energy, device_energy, device_cpu, device_memory, sdk_peer_latency, device_recovery_time, actual_worker_execution_count, trusted_clock_or_signature_provenance.

The local gate permits a separately measured SDK coordination run. It does not complete ENG-188's N=2/N=4 Ditto, heterogeneous specialist, or physical-device gates.
