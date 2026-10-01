from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-ditto-device-flow-001"
_SPEC = importlib.util.spec_from_file_location("edge_ditto_contracts", EXPERIMENT / "contracts.py")
assert _SPEC is not None and _SPEC.loader is not None
contracts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(contracts)
_PREVIOUS_CONTRACTS = sys.modules.get("contracts")
sys.modules["contracts"] = contracts
try:
    _RUN_SPEC = importlib.util.spec_from_file_location("edge_ditto_run", EXPERIMENT / "run.py")
    assert _RUN_SPEC is not None and _RUN_SPEC.loader is not None
    runner = importlib.util.module_from_spec(_RUN_SPEC)
    _RUN_SPEC.loader.exec_module(runner)
    _PEER_SPEC = importlib.util.spec_from_file_location("edge_ditto_peer", EXPERIMENT / "peer.py")
    assert _PEER_SPEC is not None and _PEER_SPEC.loader is not None
    peer_runner = importlib.util.module_from_spec(_PEER_SPEC)
    _PEER_SPEC.loader.exec_module(peer_runner)
finally:
    if _PREVIOUS_CONTRACTS is None:
        sys.modules.pop("contracts", None)
    else:
        sys.modules["contracts"] = _PREVIOUS_CONTRACTS


def _artifacts() -> tuple[dict, dict]:
    model = {
        "schema_version": 2,
        "kind": contracts.MODEL_KIND,
        "window_cycles": 20,
        "channels_per_cycle": 24,
        "feature_count": 480,
        "threshold": 0.5,
        "scaler_mean": [0.0] * 480,
        "scaler_scale": [1.0] * 480,
        "coefficients": [0.0] * 480,
        "intercept": 0.0,
    }
    model["sha256"] = contracts.payload_digest(model)
    cohort = {
        "schema_version": 2,
        "kind": contracts.COHORT_KIND,
        "model_sha256": model["sha256"],
        "rows": [
            {
                "engine_id": index,
                "features": [0.0] * 480,
                "expected_probability": 0.5,
                "expected_decision": 1,
                "rul_label": 0,
            }
            for index in range(1, 101)
        ],
    }
    cohort["sha256"] = contracts.payload_digest(cohort)
    return model, cohort


def _scenario(model_bytes: bytes, cohort_bytes: bytes) -> dict:
    scenario = json.loads((EXPERIMENT / "scenario-n2.json").read_text())
    model, cohort = json.loads(model_bytes), json.loads(cohort_bytes)
    scenario["model"].update(
        file_sha256=contracts.digest_bytes(model_bytes), payload_sha256=model["sha256"]
    )
    scenario["cohort"].update(
        file_sha256=contracts.digest_bytes(cohort_bytes), payload_sha256=cohort["sha256"]
    )
    return scenario


def _measurements(*, missing_counter: bool = False) -> dict:
    return {
        "schema_version": 1,
        "samples_ms": {name: [10.0] for name in contracts.LATENCY_METRICS},
        "write_failures": 0,
        "db_bytes": {
            "before_open": 100, "after_first_local_query": 110,
            "after_reopen": 115, "after_sync": 120,
        },
        "sdk_raw_stream_bytes": {
            "sent_delta": None if missing_counter else 12,
            "received_delta": None if missing_counter else 13,
            "unavailable_reason": "counter_missing" if missing_counter else None,
        },
    }


class EdgeDittoPeerHarnessTests(unittest.TestCase):
    def test_worker_output_whitelist_rejects_extra_or_unstructured_fields(self) -> None:
        digest = "a" * 64
        result = {
            "status": "passed",
            "peer_id": "sensor-peer-a",
            "device_id_sha256": digest,
            "sdk_version": "5.2.0.dev0",
            "sdk_distribution_sha256": "e" * 64,
            "python_version": "3.12.14",
            "platform": "linux",
            "topology": {
                "mode": "loopback",
                "listen_interface": "127.0.0.1",
                "listen_port": 22001,
                "neighbor_host": "127.0.0.1",
                "neighbor_port": 22002,
            },
            "local_persistence": "passed",
            "exact_replay": "passed",
            "synced_observation_count": 2,
            "predictions": [
                {
                    "observation_id_sha256": digest,
                    "input_id_sha256": "b" * 64,
                    "probability": 0.5,
                    "decision": 1,
                },
                {
                    "observation_id_sha256": "c" * 64,
                    "input_id_sha256": "d" * 64,
                    "probability": 0.5,
                    "decision": 1,
                },
            ],
            "elapsed_ms": 10.0,
            "measurements": _measurements(),
        }

        topology = result["topology"]
        self.assertEqual(runner._validated_result(result, "sensor-peer-a", topology), result)
        expected_predictions = {
            item["observation_id_sha256"]: item for item in result["predictions"]
        }
        self.assertEqual(
            runner._validated_result(
                result, "sensor-peer-a", topology, expected_predictions, "e" * 64, digest
            ),
            result,
        )
        self.assertIsNone(
            runner._validated_result(
                result, "sensor-peer-a", topology, expected_predictions, "f" * 64, digest
            )
        )
        self.assertIsNone(
            runner._validated_result(
                result, "sensor-peer-a", topology, expected_predictions, "e" * 64, "f" * 64
            )
        )
        fabricated = copy.deepcopy(result)
        fabricated["predictions"][0]["probability"] = 0.9
        self.assertIsNone(
            runner._validated_result(fabricated, "sensor-peer-a", topology, expected_predictions)
        )
        self.assertIsNone(
            runner._validated_result(result, "sensor-peer-a", {**topology, "listen_port": 80})
        )
        self.assertIsNone(
            runner._validated_result({**result, "debug": "unreviewed"}, "sensor-peer-a")
        )
        malformed_measurement = copy.deepcopy(result)
        malformed_measurement["measurements"]["samples_ms"]["peer_delivery"] = [float("nan")]
        self.assertIsNone(runner._validated_result(malformed_measurement, "sensor-peer-a"))
        self.assertIsNone(runner._safe_worker_result(b'{"status":"passed"}\n'))

        for field, invalid in (
            ("probability", float("nan")),
            ("probability", 1.1),
            ("probability", True),
            ("decision", 2),
        ):
            malformed = copy.deepcopy(result)
            malformed["predictions"][0][field] = invalid
            with self.subTest(field=field, invalid=invalid):
                self.assertIsNone(runner._validated_result(malformed, "sensor-peer-a"))

    def test_scenario_is_strict_versioned_n2_and_declares_tcp_edge(self) -> None:
        scenario = contracts.validate_scenario(
            json.loads((EXPERIMENT / "scenario-n2.json").read_text())
        )

        self.assertEqual(scenario["schema_version"], 2)
        self.assertEqual(
            scenario["sdk_distribution_sha256"], contracts.FROZEN_SDK_DISTRIBUTION_SHA256
        )
        self.assertEqual(len(scenario["peers"]), 2)
        self.assertEqual(scenario["topology"]["transport"], "static_tcp")
        self.assertNotEqual(scenario["peers"][0]["device_id"], scenario["peers"][1]["device_id"])
        policy = scenario["metrics_policy"]
        self.assertEqual(policy["min_samples_per_latency_metric"], 20)
        self.assertTrue(policy["require_sdk_raw_stream_counters"])
        self.assertEqual(policy["p95_ms_ceilings"]["end_to_end"], 15000)

        with self.assertRaisesRegex(ValueError, "scenario fields or version"):
            contracts.validate_scenario({**scenario, "unexpected": True})

    def test_json_contract_reader_rejects_duplicate_manifest_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "scenario.json"
            manifest.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                contracts.read_json(manifest)

    def test_frozen_scenario_rejects_self_consistent_substitute_pins_and_unsafe_peer_ids(
        self,
    ) -> None:
        scenario = contracts.read_json(EXPERIMENT / "scenario-n2.json")
        changed_pins = copy.deepcopy(scenario)
        changed_pins["model"]["file_sha256"] = "a" * 64
        changed_pins["model"]["payload_sha256"] = "b" * 64
        changed_pins["cohort"]["file_sha256"] = "c" * 64
        changed_pins["cohort"]["payload_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "frozen N=2 scenario"):
            contracts.validate_scenario(changed_pins)
        changed_sdk = {**scenario, "sdk_distribution_sha256": "f" * 64}
        with self.assertRaisesRegex(ValueError, "SDK distribution"):
            contracts.validate_scenario(changed_sdk)
        contracts.require_approved_sdk(scenario, contracts.FROZEN_SDK_DISTRIBUTION_SHA256)
        with self.assertRaisesRegex(ValueError, "installed Ditto SDK"):
            contracts.require_approved_sdk(scenario, "f" * 64)
        for peer_id in ("../escaped", "sub/path", ".", "-option", "sensor peer"):
            changed_peer = copy.deepcopy(scenario)
            changed_peer["peers"][0]["peer_id"] = peer_id
            changed_peer["topology"]["edges"][0][0] = peer_id
            with self.subTest(peer_id=peer_id), self.assertRaisesRegex(ValueError, "peer_id"):
                contracts.validate_scenario(changed_peer)

    def test_worker_result_rejects_duplicate_json_keys(self) -> None:
        result = b'EDGE_DITTO_RESULT {"status":"passed","status":"passed"}\n'
        self.assertIsNone(runner._safe_worker_result(result))
        duplicate_lines = b'EDGE_DITTO_RESULT {"status":"passed"}\n' * 2
        self.assertIsNone(runner._safe_worker_result(duplicate_lines))

    def test_staged_inputs_do_not_change_when_original_files_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = [root / name for name in ("scenario.json", "model.json", "cohort.json")]
            for path, content in zip(source, (b"scenario", b"model", b"cohort"), strict=True):
                path.write_bytes(content)
            snapshots = runner._stage_inputs(root / "staged", *source)
            source[0].write_bytes(b"changed")
            source[1].write_bytes(b"changed")
            self.assertEqual(
                [path.read_bytes() for path in snapshots], [b"scenario", b"model", b"cohort"]
            )

    def test_staged_child_code_and_index_hashes_reject_source_or_snapshot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [root / name for name in ("run.py", "peer.py", "contracts.py")]
            for path, content in zip(sources, (b"runner", b"peer", b"contracts"), strict=True):
                path.write_bytes(content)
            staged_peer, hashes = runner._stage_code(root / "staged", *sources)
            self.assertEqual(staged_peer.read_bytes(), b"peer")
            runner._verify_code_unchanged(sources, staged_peer.parent, hashes)
            sources[1].write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "code changed"):
                runner._verify_code_unchanged(sources, staged_peer.parent, hashes)
            sources[1].write_bytes(b"peer")
            staged_peer.chmod(0o644)
            staged_peer.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "code changed"):
                runner._verify_code_unchanged(sources, staged_peer.parent, hashes)

    def test_parent_startup_source_hash_rejects_edit_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sources = [Path(directory) / name for name in ("run.py", "peer.py", "contracts.py")]
            for path in sources:
                path.write_bytes(path.name.encode())
            startup = [contracts.digest_bytes(path.read_bytes()) for path in sources]
            runner._verify_startup_source(sources, startup)
            sources[2].write_bytes(b"changed after module import")
            with self.assertRaisesRegex(runner.RunIntegrityError, "source changed"):
                runner._verify_startup_source(sources, startup)

    def test_sdk_distribution_digest_covers_installed_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ditto").mkdir()
            (root / "ditto/__init__.py").write_bytes(b"package")
            (root / "ditto/native.so").write_bytes(b"native")
            fake = SimpleNamespace(
                files=[Path("ditto/__init__.py"), Path("ditto/native.so")],
                locate_file=lambda path: root / path,
            )
            original = hashlib.sha256((root / "ditto/native.so").read_bytes()).hexdigest()
            first = contracts.distribution_digest(fake)
            (root / "ditto/native.so").write_bytes(b"changed")
            self.assertNotEqual(first, contracts.distribution_digest(fake))
            self.assertNotEqual(first, original)

    def test_artifact_pins_reject_modified_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            model, cohort = _artifacts()
            model_path, cohort_path = tmp_path / "model.json", tmp_path / "cohort.json"
            model_path.write_bytes(contracts.canonical_bytes(model))
            cohort_path.write_bytes(contracts.canonical_bytes(cohort))
            scenario = _scenario(model_path.read_bytes(), cohort_path.read_bytes())

            loaded_model, loaded_cohort = contracts.load_pinned_artifacts(
                scenario, model_path, cohort_path
            )
            self.assertEqual(loaded_model["sha256"], model["sha256"])
            self.assertEqual(loaded_cohort["sha256"], cohort["sha256"])

            cohort_path.write_bytes(cohort_path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "artifact file digest"):
                contracts.load_pinned_artifacts(scenario, model_path, cohort_path)

    def test_full_cohort_inference_parity_and_stable_observation_identity(self) -> None:
        model, cohort = _artifacts()
        contracts.validate_artifacts(model, cohort)
        scores = contracts.verify_parity(model, cohort)
        self.assertEqual(len(scores), 100)
        self.assertEqual(set(scores.values()), {0.5})

        input_identity = "a" * 64
        first = contracts.observation_id("device-a", input_identity, model["sha256"])
        replay = contracts.observation_id("device-a", input_identity, model["sha256"])
        changed_device = contracts.observation_id("device-b", input_identity, model["sha256"])
        changed_input = contracts.observation_id("device-a", "b" * 64, model["sha256"])
        self.assertEqual(first, replay)
        self.assertNotEqual(first, changed_device)
        self.assertNotEqual(first, changed_input)

    def test_transport_defaults_preserve_loopback_and_distributed_requires_dns_alias(self) -> None:
        default = contracts.peer_transport("loopback", None, 22001, None, 22002)
        self.assertEqual(
            default,
            {
                "mode": "loopback",
                "listen_interface": "127.0.0.1",
                "listen_port": 22001,
                "neighbor_host": "127.0.0.1",
                "neighbor_port": 22002,
            },
        )
        distributed = contracts.peer_transport(
            "distributed", "0.0.0.0", 24225, "edge-peer-b", 24225
        )
        self.assertEqual(distributed["neighbor_host"], "edge-peer-b")
        self.assertEqual(distributed["listen_interface"], "0.0.0.0")

        invalid = (
            ("distributed", None, 24225, "edge-peer-b", 24225),
            ("distributed", "127.0.0.1", 24225, "edge-peer-b", 24225),
            ("distributed", "0.0.0.0", 24225, "127.0.0.1", 24225),
            ("distributed", "0.0.0.0", 24225, "peer-b;id", 24225),
            ("distributed", "0.0.0.0", 24225, "UPPERCASE", 24225),
            ("distributed", "0.0.0.0", 65536, "edge-peer-b", 24225),
            ("loopback", "0.0.0.0", 22001, "127.0.0.1", 22002),
        )
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                contracts.peer_transport(*args)

    def test_worker_topology_evidence_is_whitelisted_and_does_not_accept_private_fields(
        self,
    ) -> None:
        result = {
            "status": "passed",
            "peer_id": "sensor-peer-a",
            "device_id_sha256": "a" * 64,
            "sdk_version": "5.2.0.dev0",
            "sdk_distribution_sha256": "e" * 64,
            "python_version": "3.12.14",
            "platform": "linux",
            "topology": {
                "mode": "distributed",
                "listen_interface": "0.0.0.0",
                "listen_port": 24225,
                "neighbor_host": "edge-peer-b",
                "neighbor_port": 24225,
            },
            "local_persistence": "passed",
            "exact_replay": "passed",
            "synced_observation_count": 2,
            "predictions": [
                {
                    "observation_id_sha256": "b" * 64,
                    "input_id_sha256": "c" * 64,
                    "probability": 0.5,
                    "decision": 1,
                },
                {
                    "observation_id_sha256": "d" * 64,
                    "input_id_sha256": "e" * 64,
                    "probability": 0.5,
                    "decision": 1,
                },
            ],
            "elapsed_ms": 10.0,
            "measurements": _measurements(),
        }
        self.assertEqual(runner._validated_result(result, "sensor-peer-a"), result)
        self.assertIsNone(
            runner._validated_result({**result, "license": "unreviewed"}, "sensor-peer-a")
        )

    def test_same_id_replay_requires_exact_immutable_content(self) -> None:
        original = {"_id": "stable", "schema_version": 1, "probability": 0.75}
        contracts.assert_same_immutable_content(original, copy.deepcopy(original))

        with self.assertRaisesRegex(ValueError, "same-ID observation content conflict"):
            contracts.assert_same_immutable_content(original, {**original, "probability": 0.25})

    def test_typed_observation_uses_stable_id_and_excludes_raw_features(self) -> None:
        model, cohort = _artifacts()
        scenario = {"scenario_id": "edge-ditto-device-flow-001-n2-fd001"}
        peer = {"device_id": "device-a", "engine_id": 1}

        document = contracts.observation_document(scenario, peer, model, cohort, 0.5)
        replay = contracts.observation_document(scenario, peer, model, cohort, 0.5)

        self.assertEqual(document, replay)
        self.assertIs(type(document["decision"]), int)
        self.assertIs(type(document["probability"]), float)
        self.assertNotIn("features", document)
        self.assertNotIn("rul_label", document)
        self.assertEqual(
            document["_id"],
            contracts.observation_id("device-a", document["input_id_sha256"], model["sha256"]),
        )

    def test_artifact_parity_rejects_prediction_drift(self) -> None:
        model, cohort = _artifacts()
        bad_cohort = copy.deepcopy(cohort)
        bad_cohort["rows"][0]["expected_probability"] = 0.9

        with self.assertRaisesRegex(ValueError, "prediction parity failed for engine 1"):
            contracts.verify_parity(model, bad_cohort)

    def test_license_gate_is_not_reported_as_sdk_evidence(self) -> None:
        # These tests never read a license or open a real SDK peer. A run manifest
        # reports SDK evidence only after both worker processes pass persistence and sync.
        source = (EXPERIMENT / "run.py").read_text()
        self.assertIn('"sdk_integration_verified": status == "passed"', source)
        self.assertNotIn("Ditto.open", source)

    def test_measurement_boundary_rejects_unbounded_and_malformed_evidence(self) -> None:
        valid = _measurements()
        self.assertEqual(contracts.validate_measurements(valid), valid)
        variants = []
        for field, bad in (("selected_row_inference", [float("nan")]),
                           ("peer_delivery", [True]), ("end_to_end", [1.0, 2.0])):
            changed = copy.deepcopy(valid)
            changed["samples_ms"][field] = bad
            variants.append(changed)
        for field, bad in (("before_open", -1), ("after_sync", True)):
            changed = copy.deepcopy(valid)
            changed["db_bytes"][field] = bad
            variants.append(changed)
        changed = copy.deepcopy(valid)
        changed["sdk_raw_stream_bytes"]["debug"] = "secret"
        variants.append(changed)
        changed = copy.deepcopy(valid)
        changed["sdk_raw_stream_bytes"]["sent_delta"] = None
        variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                contracts.validate_measurements(changed)

    def test_sdk_counter_parser_sums_series_and_fails_closed(self) -> None:
        rows = [
            {"key": "ditto.stream.raw_bytes_sent", "labels": {"peer": "a"}, "current": 5},
            {"key": "ditto.stream.raw_bytes_sent", "labels": {"peer": "b"}, "current": 7},
            {"key": "ditto.stream.raw_bytes_received", "labels": {}, "current": 13},
        ]
        self.assertEqual(contracts.aggregate_raw_stream_counters(rows, allow_missing=False),
                         {"sent": 12, "received": 13})
        self.assertEqual(contracts.aggregate_raw_stream_counters([], allow_missing=True),
                         {"sent": 0, "received": 0})
        with self.assertRaisesRegex(ValueError, "counter_missing"):
            contracts.aggregate_raw_stream_counters(rows[:2], allow_missing=False)
        with self.assertRaisesRegex(ValueError, "schema_unexpected"):
            contracts.aggregate_raw_stream_counters([{"key": rows[0]["key"],
                "labels": {}, "current": True}], allow_missing=False)
        with self.assertRaisesRegex(ValueError, "schema_unexpected"):
            contracts.aggregate_raw_stream_counters([rows[0], rows[0], rows[2]],
                                                     allow_missing=False)
        self.assertEqual(peer_runner._raw_delta({"sent": {"a": 3}, "received": {"a": 4}},
                                               {"sent": {"a": 12}, "received": {"a": 13}}, None),
                         {"sent_delta": 9, "received_delta": 9,
                          "unavailable_reason": None})
        self.assertEqual(peer_runner._raw_delta(
            {"sent": {"a": 13, "b": 5}, "received": {"a": 4}},
            {"sent": {"a": 12, "b": 50}, "received": {"a": 13}}, None),
                         {"sent_delta": None, "received_delta": None,
                          "unavailable_reason": "counter_reset"})
        self.assertEqual(peer_runner._raw_delta(
            {"sent": {"old": 5}, "received": {"a": 4}},
            {"sent": {"new": 50}, "received": {"a": 13}}, None),
            {"sent_delta": None, "received_delta": None,
             "unavailable_reason": "series_changed"})

    def test_two_peer_metrics_are_insufficient_for_predeclared_performance_gate(self) -> None:
        policy = contracts.validate_scenario(contracts.read_json(EXPERIMENT / "scenario-n2.json"))["metrics_policy"]
        peers = [
            {"status": "passed", "peer_id": name, "measurements": _measurements()}
            for name in ("sensor-peer-a", "sensor-peer-b")
        ]
        summary = runner.summarize_performance(peers, policy)
        self.assertEqual(summary["status"], "insufficient_samples")
        self.assertFalse(summary["closure_ready"])
        self.assertEqual(summary["latencies"]["end_to_end"],
                         {"sample_count": 2, "p50_ms": 10.0, "p95_ms": 10.0})
        self.assertEqual(summary["peer_resources"][0]["db_growth_bytes"], 20)
        self.assertEqual(summary["peer_resources"][0]["db_peak_growth_bytes"], 20)
        self.assertEqual(summary["sample_sufficiency"], "insufficient_samples")
        peers[1]["measurements"] = _measurements(missing_counter=True)
        unavailable = runner.summarize_performance(peers, policy)
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["unavailable"],
                         [{"peer_id": "sensor-peer-b", "reason": "counter_missing"}])
        self.assertEqual(unavailable["sample_sufficiency"], "insufficient_samples")

    def test_resource_violations_are_explicit_even_with_too_few_samples(self) -> None:
        policy = contracts.read_json(EXPERIMENT / "scenario-n2.json")["metrics_policy"]
        measured = _measurements()
        measured["db_bytes"]["after_sync"] = policy["max_db_growth_bytes"] + 101
        measured["sdk_raw_stream_bytes"]["sent_delta"] = policy["max_sdk_raw_stream_bytes_sent"] + 1
        peer = {"status": "passed", "peer_id": "sensor-peer-a", "measurements": measured}
        summary = runner.summarize_performance([peer], policy)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["threshold_violations"],
                         ["sensor-peer-a:db_peak_growth_bytes",
                          "sensor-peer-a:sdk_raw_stream_bytes_sent"])
        self.assertFalse(summary["closure_ready"])
        self.assertEqual(summary["sample_sufficiency"], "insufficient_samples")

    def test_peak_database_growth_fails_when_final_size_shrinks(self) -> None:
        policy = contracts.read_json(EXPERIMENT / "scenario-n2.json")["metrics_policy"]
        measured = _measurements()
        measured["db_bytes"]["after_first_local_query"] = policy["max_db_growth_bytes"] + 101
        measured["db_bytes"]["after_sync"] = 120
        summary = runner.summarize_performance(
            [{"status": "passed", "peer_id": "sensor-peer-a", "measurements": measured}], policy)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["peer_resources"][0]["db_growth_bytes"], 20)
        self.assertGreater(summary["peer_resources"][0]["db_peak_growth_bytes"],
                           policy["max_db_growth_bytes"])

    def test_observed_latency_exceedance_remains_provisional_below_sample_floor(self) -> None:
        policy = contracts.read_json(EXPERIMENT / "scenario-n2.json")["metrics_policy"]
        measured = _measurements()
        measured["samples_ms"]["selected_row_inference"] = [101.0]
        summary = runner.summarize_performance(
            [{"status": "passed", "peer_id": "sensor-peer-a", "measurements": measured}], policy)
        self.assertEqual(summary["status"], "insufficient_samples")
        self.assertEqual(summary["threshold_violations"], [])
        self.assertEqual(summary["observed_latency_exceedances"],
                         ["p95_selected_row_inference"])
        self.assertTrue(summary["latency_exceedances_provisional"])

    def test_failure_result_preserves_bounded_write_failure_count(self) -> None:
        self.assertEqual(runner._validated_result(
            {"status": "failed", "error_type": "LocalWriteFailure", "write_failures": 1},
            "sensor-peer-a"),
            {"status": "failed", "peer_id": "sensor-peer-a",
             "error_type": "LocalWriteFailure", "write_failures": 1})
        self.assertIsNone(runner._validated_result(
            {"status": "failed", "error_type": "LocalWriteFailure", "write_failures": True},
            "sensor-peer-a"))
        self.assertIsNone(runner._validated_result(
            {"status": "failed", "error_type": None, "write_failures": 0},
            "sensor-peer-a"))
