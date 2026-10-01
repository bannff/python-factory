from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from argparse import Namespace
from pathlib import Path
from types import ModuleType
from typing import Iterator

EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-visual-quality-mesh-001"


@contextmanager
def _dependency_aliases(dependencies: dict[str, ModuleType]) -> Iterator[None]:
    """Expose experiment dependencies only while a legacy absolute import loads."""
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in dependencies}
    try:
        sys.modules.update(dependencies)
        yield
    finally:
        for name, module in previous.items():
            if module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _load_experiment_module(name: str, dependencies: dict[str, ModuleType] | None = None) -> ModuleType:
    """Load a source module under a test-specific name without changing sys.path."""
    module_name = f"edge_visual_quality_mesh_test_{name}"
    spec = importlib.util.spec_from_file_location(module_name, EXPERIMENT / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load edge visual mesh module: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with _dependency_aliases(dependencies or {}):
            spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


records = _load_experiment_module("records")
manifest = _load_experiment_module("manifest", {"records": records})
prepare = _load_experiment_module("prepare", {"manifest": manifest, "records": records})
peer = _load_experiment_module("peer", {"records": records})
review = _load_experiment_module("review", {"peer": peer, "records": records})


def _rows() -> list[dict]:
    return [
        {
            "path": f"item-{item}/image-{index}.jpg",
            "item_id": f"item-{item}",
            "image_sha256": f"{item * 10 + index:064x}",
            "label": index % 2,
        }
        for item, count in ((1, 3), (2, 2), (3, 2), (4, 1))
        for index in range(count)
    ]


class EdgeVisualMeshRunnerTests(unittest.TestCase):
    def test_manifest_is_deterministic_whole_item_and_label_separated(self) -> None:
        sha = "a" * 64
        first, labels = manifest.freeze_manifest(
            _rows(), round_id="round-01", model_sha256=sha,
            source_sha256="b" * 64, split_sha256="c" * 64,
        )
        repeated, repeated_labels = manifest.freeze_manifest(
            reversed(_rows()), round_id="round-01", model_sha256=sha,
            source_sha256="b" * 64, split_sha256="c" * 64,
        )
        self.assertEqual(first, repeated)
        self.assertEqual(labels, repeated_labels)
        owners: dict[str, set[str]] = {}
        for task in first["tasks"]:
            owners.setdefault(task["item_id"], set()).add(task["owner_peer"])
        self.assertTrue(all(len(value) == 1 for value in owners.values()))
        self.assertEqual(first["task_count"], len({task["task_id"] for task in first["tasks"]}))
        self.assertEqual(first["peer_task_counts"], {
            peer_id: sum(task["owner_peer"] == peer_id for task in first["tasks"])
            for peer_id in manifest.PEERS
        })
        peer_doc = manifest.peer_manifest(first, "inspection-a", labels["relative_paths"])
        self.assertNotIn("labels", peer_doc)
        self.assertNotIn("label", json.dumps(peer_doc).lower())
        self.assertEqual(set(labels["labels"]), {task["image_id"] for task in first["tasks"]})

    def test_manifest_rejects_duplicate_paths_and_escape_paths(self) -> None:
        sha = "a" * 64
        rows = _rows()
        rows[1]["path"] = rows[0]["path"]
        with self.assertRaises(ValueError):
            manifest.freeze_manifest(rows, round_id="r", model_sha256=sha,
                                     source_sha256=sha, split_sha256=sha)
        rows = _rows()
        rows[0]["path"] = "../outside.jpg"
        with self.assertRaises(ValueError):
            manifest.freeze_manifest(rows, round_id="r", model_sha256=sha,
                                     source_sha256=sha, split_sha256=sha)

    def test_record_replay_is_idempotent_and_conflicting_replay_fails(self) -> None:
        sha = "a" * 64
        doc = records.make_record(
            "result", "r", "task-1", task_id="task-1", item_id="part-1",
            image_id="opaque-1", image_sha256=sha, source_peer="inspection-a",
            model_sha256=sha, score=0.25, decision=0,
            write_started_at_utc="2026-09-30T12:00:00+00:00",
        )
        self.assertEqual(records.assert_idempotent(None, doc), "new")
        self.assertEqual(records.assert_idempotent(doc, doc), "duplicate")
        changed = {**doc, "score": 0.75, "decision": 1}
        with self.assertRaisesRegex(ValueError, "different immutable content"):
            records.assert_idempotent(doc, changed)

    def test_records_reject_private_fields_and_invalid_scores(self) -> None:
        sha = "a" * 64
        with self.assertRaisesRegex(ValueError, "private data"):
            records.make_record(
                "result", "r", "task-1", task_id="task-1", item_id="i", image_id="x",
                image_sha256=sha, source_peer="inspection-a", model_sha256=sha,
                score=0.5, decision=1, write_started_at_utc="2026-09-30T12:00:00+00:00",
                relative_path="item/image.jpg",
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            records.make_record(
                "result", "r", "task-1", task_id="task-1", item_id="i", image_id="x",
                image_sha256=sha, source_peer="inspection-a", model_sha256=sha,
                score=float("nan"), decision=1,
                write_started_at_utc="2026-09-30T12:00:00+00:00",
            )

    def test_peer_cli_boundaries_require_assigned_files_and_dns_peer(self) -> None:
        sha = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "item").mkdir()
            (root / "item/image.jpg").write_bytes(b"source image")
            task = {
                "task_id": "r:x", "item_id": "item", "image_id": "x",
                "owner_peer": "inspection-a", "relative_path": "item/image.jpg",
                "image_sha256": sha,
            }
            assignment = {
                "schema_version": 1, "round_id": "r", "assignment_sha256": sha,
                "model_sha256": sha, "peer_id": "inspection-a", "tasks": [task],
            }
            manifest_path = root / "peer.json"
            manifest_path.write_text(json.dumps(assignment))
            options = Namespace(
                peer_id="inspection-a", listen_interface="0.0.0.0", port=22001,
                neighbor_port=22002, neighbor_host="inspection-b", database_id="b1db20b1-24c8-4cba-a5bd-2178a2b9f711",
                images=root, manifest=manifest_path,
            )
            loaded, paths = peer.validate_options(options)
            self.assertEqual(loaded["peer_id"], "inspection-a")
            self.assertEqual(paths["image_root"], root.resolve())
            options.neighbor_host = "10.0.0.2"
            with self.assertRaisesRegex(ValueError, "DNS alias"):
                peer.validate_options(options)
            options.neighbor_host = "inspection-b"
            options.peer_id = "inspection-c"
            with self.assertRaisesRegex(ValueError, "outside the frozen roster"):
                peer.validate_options(options)

    def test_progress_snapshot_represents_missing_sync_as_waiting(self) -> None:
        snapshot = peer.snapshot_from_documents(
            {}, round_id="r", peer_id="inspection-a", inference_count=2, state="waiting"
        )
        self.assertEqual(snapshot["state"], "waiting")
        self.assertEqual(snapshot["evidence"], "ditto_store_read")
        self.assertEqual(snapshot["join_record_state"], {
            "inspection-a": "waiting", "inspection-b": "waiting",
        })
        self.assertEqual(snapshot["replicated_result_count"], 0)
        self.assertEqual(snapshot["local_inference_count"], 2)
        self.assertEqual(snapshot["stale_after_seconds"], 5)
        self.assertIsNotNone(snapshot["observed_at_utc"])

    def test_host_preparation_separates_labels_and_stages_owned_originals(self) -> None:
        model_bytes = (EXPERIMENT / "model-fold0.json").read_bytes()
        inventory = []
        for row in _rows():
            original = f"original:{row['path']}".encode()
            inventory.append({
                "path": row["path"], "item_id": row["item_id"],
                "image_sha256": hashlib.sha256(original).hexdigest(),
                "label": row["label"], "image_bytes": original,
            })
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "prepared"
            summary = prepare.prepare_bundles(
                inventory, model_bytes=model_bytes,
                source_hashes=prepare.SOURCE_HASHES,
                round_id="round-prepare", out=out, verified_official=True,
            )
            self.assertEqual(summary["task_count"], len(inventory))
            labels = json.loads((out / "host/host-labels.json").read_text())
            assignment = json.loads((out / "host/assignment-manifest.json").read_text())
            self.assertEqual(len(labels["labels"]), len(inventory))
            self.assertNotIn("label", json.dumps(assignment).lower())
            for peer_id in manifest.PEERS:
                bundle = out / "peers" / peer_id
                local = json.loads((bundle / "manifest.json").read_text())
                full = json.loads((bundle / "assignment-manifest.json").read_text())
                self.assertEqual(full, assignment)
                self.assertTrue(all(task["owner_peer"] == peer_id for task in local["tasks"]))
                self.assertNotIn("label", json.dumps(local).lower())
                self.assertTrue(all("relative_path" not in task for task in full["tasks"]))
                remote_peer = "inspection-b" if peer_id == "inspection-a" else "inspection-a"
                remote_paths = {
                    task["relative_path"] for task in manifest.peer_manifest(
                        assignment, remote_peer, labels["relative_paths"],
                    )["tasks"]
                }
                full_text = (bundle / "assignment-manifest.json").read_text()
                self.assertTrue(all(path not in full_text for path in remote_paths))
                staged = {path.relative_to(bundle / "images").as_posix()
                          for path in (bundle / "images").rglob("*.jpg")}
                self.assertEqual(staged, {task["relative_path"] for task in local["tasks"]})
                self.assertEqual((bundle / "model-fold0.json").read_bytes(), model_bytes)

    def test_host_inventory_reader_verifies_local_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_root = root / "images"
            rows = []
            for index in range(135):
                item = f"item-{index // 8:02d}"
                relative = f"{item}/image-{index:03d}.jpg"
                image = f"original-{index}".encode()
                path = image_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(image)
                rows.append({
                    "path": relative, "item_id": item,
                    "image_sha256": hashlib.sha256(image).hexdigest(),
                    "label": int(index < 18),
                })
            inventory_path = root / "inventory.json"
            inventory_path.write_text(json.dumps({
                "schema_version": 1, "dataset": "KolektorSDD", "fold": 0,
                "source_sha256": prepare.SOURCE_HASHES["KolektorSDD.zip"],
                "split_sha256": prepare.SOURCE_HASHES["KolektorSDD-training-splits.zip"],
                "rows": rows,
            }))
            official = [dict(row) for row in rows]
            with patch.object(prepare, "fold0_inventory", return_value=(official, prepare.SOURCE_HASHES)):
                loaded, hashes = prepare.read_host_inventory(inventory_path, image_root, root)
            self.assertEqual(len(loaded), 135)
            self.assertEqual(sum(row["label"] for row in loaded), 18)
            self.assertEqual(loaded[0]["image_bytes"], b"original-0")
            self.assertEqual(hashes, prepare.SOURCE_HASHES)

    def test_inventory_must_match_official_paths_hashes_and_labels(self) -> None:
        official = _rows()
        prepare.validate_inventory_rows(official, official)
        for field, value in (("label", 1 - official[0]["label"]),
                             ("image_sha256", "f" * 64), ("path", "other/image.jpg")):
            changed = [dict(row) for row in official]
            changed[0][field] = value
            with self.assertRaisesRegex(ValueError, "official fold-0"):
                prepare.validate_inventory_rows(changed, official)

    def test_convergence_requires_exact_round_event_sets(self) -> None:
        common = {
            "round:r:r": {"kind": "round", "task_ids": ["t1"], "task_count": 1,
                          "peer_ids": ["inspection-a", "inspection-b"]},
            "join:r:inspection-a": {"kind": "join"},
            "join:r:inspection-b": {"kind": "join"},
            "task_claim:r:t1": {"kind": "task_claim"},
            "result:r:t1": {"kind": "result", "task_id": "t1", "decision": 0},
        }
        args = dict(round_id="r", expected_task_ids={"t1"},
                    expected_result_ids={"result:r:t1"},
                    expected_claim_ids={"task_claim:r:t1"},
                    expected_join_ids={"join:r:inspection-a", "join:r:inspection-b"})
        self.assertTrue(peer.validate_round_sets(common, **args))
        with self.assertRaisesRegex(ValueError, "unexpected result"):
            peer.validate_round_sets({**common, "result:r:extra": {"kind": "result"}}, **args)
        with self.assertRaisesRegex(ValueError, "round record"):
            peer.validate_round_sets({**common, "round:r:extra": {"kind": "round"}}, **args)

    def test_sync_latency_is_measured_against_sixty_second_gate(self) -> None:
        start = "2026-09-30T12:00:00+00:00"
        self.assertEqual(peer.sync_latency_seconds(start, "2026-09-30T12:01:00+00:00"), 60)
        self.assertGreater(peer.sync_latency_seconds(start, "2026-09-30T12:01:00.001000+00:00"), 60)

    def test_replay_does_not_remeasure_old_remote_sync_latency(self) -> None:
        result = {
            "result:r:t1": {
                "source_peer": "inspection-b",
                "write_started_at_utc": "2026-09-30T12:00:00+00:00",
            },
        }
        seen = {"result:r:t1": "2026-09-30T14:00:00+00:00"}
        self.assertEqual(peer.remote_sync_evidence(
            result, seen, peer_id="inspection-a", restart_replay=True,
        ), ("not_measured_replay", []))
        with self.assertRaises(peer.SyncGateError):
            peer.remote_sync_evidence(
                result, seen, peer_id="inspection-a", restart_replay=False,
            )

    def test_converged_records_must_reference_frozen_tasks_and_results(self) -> None:
        sha = "a" * 64
        task = {
            "task_id": "t1", "owner_peer": "inspection-a", "item_id": "item",
            "image_id": "image", "image_sha256": sha,
        }
        docs = {
            "round:r:r": records.make_record(
                "round", "r", "r", peer_ids=["inspection-a", "inspection-b"],
                task_ids=["t1"], task_count=1, assignment_sha256=sha,
                model_sha256=sha,
            ),
            "join:r:inspection-a": records.make_record(
                "join", "r", "inspection-a", peer_id="inspection-a",
            ),
            "join:r:inspection-b": records.make_record(
                "join", "r", "inspection-b", peer_id="inspection-b",
            ),
            "task_claim:r:t1": records.make_record(
                "task_claim", "r", "t1", task_id="t1", owner_peer="inspection-a",
            ),
            "result:r:t1": records.make_record(
                "result", "r", "t1", task_id="t1", item_id="item", image_id="image",
                image_sha256=sha, source_peer="inspection-a", model_sha256=sha,
                score=0.8, decision=1, write_started_at_utc="2026-09-30T12:00:00+00:00",
            ),
            "review_open:r:t1": records.make_record(
                "review_open", "r", "t1", observation_id="result:r:t1",
                task_id="t1", status="open", reason="model_flagged_for_human_review",
            ),
            "review_decision:r:t1:r1:inspection-b": records.make_record(
                "review_decision", "r", "t1:r1:inspection-b",
                observation_id="result:r:t1", task_id="t1", reviewer_id="inspection-b",
                decision="review", revision=1,
            ),
        }
        kwargs = dict(round_id="r", tasks={"t1": task}, model_sha=sha, assignment_sha=sha)
        peer.validate_round_links(docs, **kwargs)
        altered = {**docs, "review_open:r:t1": {
            **docs["review_open:r:t1"], "observation_id": "result:r:other",
        }}
        with self.assertRaisesRegex(ValueError, "review observation"):
            peer.validate_round_links(altered, **kwargs)
        altered = {**docs, "join:r:inspection-b": {
            **docs["join:r:inspection-b"], "peer_id": "inspection-a",
        }}
        with self.assertRaisesRegex(ValueError, "join peer"):
            peer.validate_round_links(altered, **kwargs)
        altered = {**docs, "round:r:r": {
            **docs["round:r:r"], "assignment_sha256": "b" * 64,
        }}
        with self.assertRaisesRegex(ValueError, "round hashes"):
            peer.validate_round_links(altered, **kwargs)

    def test_review_decisions_require_stable_contiguous_conflict_free_revisions(self) -> None:
        first = review.review_record(
            round_id="r", task_id="task", observation_id="result:r:task",
            reviewer_id="inspection-a", decision="review", revision=1,
        )
        self.assertEqual(review.validate_next_review([], first), "new")
        self.assertEqual(review.validate_next_review([first], first), "duplicate")
        second = review.review_record(
            round_id="r", task_id="task", observation_id="result:r:task",
            reviewer_id="inspection-a", decision="dismiss", revision=2,
        )
        self.assertEqual(review.validate_next_review([first], second), "new")
        gap = review.review_record(
            round_id="r", task_id="task", observation_id="result:r:task",
            reviewer_id="inspection-a", decision="dismiss", revision=3,
        )
        with self.assertRaisesRegex(ValueError, "next revision"):
            review.validate_next_review([first], gap)
        contender = review.review_record(
            round_id="r", task_id="task", observation_id="result:r:task",
            reviewer_id="inspection-b", decision="dismiss", revision=1,
        )
        with self.assertRaisesRegex(ValueError, "revision"):
            review.validate_next_review([first], contender)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            records.validate_review_history([first, contender])
        self.assertEqual(review.replication_status(first, {"inspection-a": first}), "incomplete")
        self.assertEqual(review.replication_status(first, {
            "inspection-a": first, "inspection-b": first,
        }), "passed")
        self.assertEqual(review.replication_status(first, {
            "inspection-a": first, "inspection-b": contender,
        }), "failed")
        self.assertEqual(review.replication_status(first, {"inspection-a": first}), "incomplete")
        self.assertEqual(review.replication_status(first, {
            "inspection-a": first, "inspection-b": first,
        }), "passed")
        self.assertEqual(review.replication_status(first, {
            "inspection-a": first, "inspection-b": contender,
        }), "failed")

    def test_restart_guard_requires_persisted_results_and_zero_new_writes(self) -> None:
        expected = {"result:r:t1", "result:r:t2"}
        peer.require_fresh_sync_round(set())
        with self.assertRaisesRegex(ValueError, "no persisted results"):
            peer.require_fresh_sync_round({"result:r:t1"})
        with self.assertRaisesRegex(ValueError, "persistent store"):
            peer.require_replay_ready(expected, {"result:r:t1"})
        peer.require_replay_ready(expected, expected)
        self.assertEqual(peer.verify_replay_result(
            expected, expected, expected, {"new": 0, "duplicate": 4},
        ), 0)
        with self.assertRaisesRegex(ValueError, "new write"):
            peer.verify_replay_result(
                expected, expected, expected, {"new": 1, "duplicate": 3},
            )

    def test_task_claim_is_confirmed_before_local_inference(self) -> None:
        class QueryResult:
            def __init__(self, values):
                self.values = values

            def __iter__(self):
                return iter(self.values)

            def close(self):
                pass

        class Store:
            def __init__(self, events):
                self.events = events
                self.docs = {}

            async def execute(self, query, params=None):
                if query.startswith("SELECT"):
                    self.events.append("read")
                    rows = [type("Row", (), {"value": value}) for value in self.docs.values()]
                    return QueryResult(rows)
                self.events.append("write")
                value = params["document"]
                self.docs.setdefault(value["_id"], value)
                return QueryResult([])

        class FakePeer:
            def __init__(self, events):
                self.store = Store(events)

        async def exercise_ordering():
            events = []
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                image = b"local image bytes"
                (root / "image.jpg").write_bytes(image)
                sha = hashlib.sha256(image).hexdigest()
                task = {
                    "task_id": "task-1", "item_id": "item-1", "image_id": "opaque-1",
                    "owner_peer": "inspection-a", "relative_path": "image.jpg",
                    "image_sha256": sha,
                }

                def infer(image_bytes, model_value):
                    self.assertEqual(image_bytes, image)
                    events.append("infer")
                    return {"probability": 0.2, "decision": 0}

                persistent_peer = FakePeer(events)
                first_tally = {"new": 0, "duplicate": 0}
                first_result = await peer._process_task(
                    persistent_peer, task, image_root=root, round_id="round-1",
                    owner_peer="inspection-a", model={}, model_sha="a" * 64,
                    infer=infer, write_tally=first_tally,
                )
                self.assertEqual(first_tally, {"new": 2, "duplicate": 0})
                first_inference = events.index("infer")
                self.assertEqual(events[first_inference - 3:first_inference], ["read", "write", "read"])
                self.assertEqual(events[first_inference + 1:first_inference + 5],
                                 ["read", "read", "write", "read"])
                events.clear()
                replay_tally = {"new": 0, "duplicate": 0}
                replay_result = await peer._process_task(
                    persistent_peer, task, image_root=root, round_id="round-1",
                    owner_peer="inspection-a", model={}, model_sha="a" * 64,
                    infer=infer, write_tally=replay_tally,
                )
                self.assertEqual(first_result, replay_result)
                self.assertEqual(replay_tally, {"new": 0, "duplicate": 2})
                self.assertEqual(len(persistent_peer.store.docs), 2)
            inference_indices = [index for index, event in enumerate(events) if event == "infer"]
            self.assertEqual(len(inference_indices), 1)
            index = inference_indices[0]
            self.assertEqual(events[:index], ["read"])
            self.assertEqual(events[index + 1:], ["read", "read"])

        asyncio.run(exercise_ordering())


if __name__ == "__main__":
    unittest.main()
