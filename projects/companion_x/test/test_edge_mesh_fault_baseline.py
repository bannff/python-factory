"""Outcome checks for the frozen, model-independent local fault corpus."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "experiments/edge_models/edge-mesh-coordinator-001"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"edge_mesh_{name}_test", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


corpus = _module("fault_corpus")
baseline = _module("run_baseline")


def test_frozen_corpus_is_reproducible_and_pinned() -> None:
    frozen = corpus.load_frozen()
    assert corpus.corpus_bytes(corpus.build_corpus()) == (ROOT / "fault-corpus-v1.json").read_bytes()
    assert corpus.corpus_sha256(frozen) == corpus.FROZEN_SHA256
    assert {case["case_id"] for case in frozen["cases"]} >= {
        "local-eligible", "remote-eligible", "stale-capability", "duplicate-delivery",
        "claim-race", "expired-claim", "peer-loss", "peer-rejoin", "cross-session",
        "same-id-conflict", "post-expiry-replay", "reclaim-after-expiry",
        "unavailable-remote", "result-owner-mismatch", "three-way-race",
        "lost-peer-historical-completion",
        "capability-unavailable-transition", "claim-withdrawal-transition",
        "late-completion-revision-race", "membership-interrupted-rejoin",
        "delayed-result-recording", "delayed-claim-recording",
        "result-before-claim-persistence",
        "claim-issued-while-absent",
    }
    assert {case["topology"] for case in frozen["cases"]} == {1, 2, 4}
    assert {case["split"] for case in frozen["cases"]} == {"development", "held-out"}
    policy_sha256 = hashlib.sha256((ROOT / "policy-v1.json").read_bytes()).hexdigest()
    assert corpus.POLICY_SHA256 == policy_sha256 == frozen["policy_sha256"]
    assert all(row["policy_sha256"] == policy_sha256
               for case in frozen["cases"] for row in case["records"]
               if row["record_type"] in {"task", "result"})


@pytest.mark.parametrize("case_id", [
    "local-eligible", "remote-eligible", "stale-capability", "duplicate-delivery",
    "claim-race", "expired-claim", "peer-loss", "peer-rejoin", "cross-session",
    "same-id-conflict", "post-expiry-replay", "reclaim-after-expiry",
    "unavailable-remote", "result-owner-mismatch", "three-way-race",
    "lost-peer-historical-completion",
    "capability-unavailable-transition", "claim-withdrawal-transition",
    "late-completion-revision-race", "membership-interrupted-rejoin",
    "delayed-result-recording", "delayed-claim-recording",
    "result-before-claim-persistence",
    "claim-issued-while-absent",
])
def test_case_matches_frozen_expected_outcomes(case_id: str) -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == case_id)
    observed = baseline.evaluate_case(case, replay_seed=20260930, replay_count=12)
    assert observed["coordinator"]["state"] == case["expected"]["coordinator_state"]
    assert observed["coordinator"]["selected_peer"] == case["expected"]["selected_peer"]
    assert observed["baseline"]["state"] == case["expected"]["baseline_state"]
    assert observed["replay_equal"] is True
    assert observed["unsafe_routes"] == 0
    assert observed["accepted_stale_claims"] == 0
    assert observed["duplicate_accepted_results"] == 0


def test_duplicate_delivery_is_idempotent() -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == "duplicate-delivery")
    observed = baseline.evaluate_case(case, replay_seed=9, replay_count=10)
    assert observed["coordinator"]["accepted_result_count"] == 1
    assert observed["coordinator"]["state"] == "completed"
    assert len(case["records"]) > len({row["record_id"] for row in case["records"]})


def test_same_id_payload_collision_fails_closed() -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == "same-id-conflict")
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert observed["coordinator"]["state"] == "integrity_error"
    assert observed["coordinator"]["accepted_result_count"] == 0


def test_after_expiry_replay_preserves_historical_completion() -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == "post-expiry-replay")
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert observed["coordinator"]["state"] == "completed"
    assert observed["coordinator"]["accepted_result_count"] == 1


def test_expired_revision_can_be_reclaimed_without_accepting_old_claim() -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == "reclaim-after-expiry")
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert observed["coordinator"]["state"] == "completed"
    assert {row["reason"] for row in observed["coordinator"]["claim_decisions"]} == {
        "winner", "stale_task_revision",
    }


def test_late_completion_race_keeps_historical_result_without_execution_claim() -> None:
    case = next(case for case in corpus.load_frozen()["cases"]
                if case["case_id"] == "late-completion-revision-race")
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert observed["coordinator"]["task_revision"] == 0
    assert observed["coordinator"]["accepted_result_id"] == case["expected"]["accepted_result_id"]
    assert observed["competing_completed_result_proposals"] == 1
    assert observed["duplicate_accepted_results"] == 0
    assert {row["reason"] for row in observed["coordinator"]["result_decisions"]} == {
        "accepted", "stale_task_revision",
    }


def test_rejoin_requires_new_claim_after_membership_gap() -> None:
    case = next(case for case in corpus.load_frozen()["cases"]
                if case["case_id"] == "membership-interrupted-rejoin")
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert {row["reason"] for row in observed["coordinator"]["claim_decisions"]} == {
        "membership_interrupted", "winner",
    }
    assert observed["coordinator"]["accepted_result_count"] == 1


@pytest.mark.parametrize(("case_id", "kind", "earlier"), [
    ("delayed-result-recording", "result", "completed_at"),
    ("delayed-claim-recording", "claim", "issued_at"),
])
def test_delayed_recording_preserves_event_time(case_id: str, kind: str, earlier: str) -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == case_id)
    record = next(row for row in case["records"] if row["record_type"] == kind)
    assert record[earlier] < record["created_at"]
    if case_id == "delayed-result-recording":
        task = next(row for row in case["records"] if row["record_type"] == "task")
        claim = next(row for row in case["records"] if row["record_type"] == "claim")
        assert task["expires_at"] < record["created_at"]
        assert claim["expires_at"] < record["created_at"]
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)
    assert observed["coordinator"]["accepted_result_count"] == 1


def test_result_before_claim_recording_is_rejected() -> None:
    case = next(case for case in corpus.load_frozen()["cases"]
                if case["case_id"] == "result-before-claim-persistence")
    claim = next(row for row in case["records"] if row["record_type"] == "claim")
    result = next(row for row in case["records"] if row["record_type"] == "result")
    assert result["completed_at"] < claim["created_at"]
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)["coordinator"]
    assert observed["state"] == "active"
    assert observed["accepted_result_count"] == 0
    assert {row["reason"] for row in observed["result_decisions"]} == {
        "claim_not_recorded_at_completion",
    }


def test_claim_recorded_after_rejoin_cannot_gain_retroactive_authority() -> None:
    case = next(case for case in corpus.load_frozen()["cases"]
                if case["case_id"] == "claim-issued-while-absent")
    claim = next(row for row in case["records"] if row["record_type"] == "claim")
    epochs = sorted((row for row in case["records"] if row["record_type"] == "session"),
                    key=lambda row: row["membership_epoch"])
    assert epochs[1]["opened_at"] < claim["issued_at"] < epochs[2]["opened_at"] < claim["created_at"]
    observed = baseline.evaluate_case(case, replay_seed=17, replay_count=10)["coordinator"]
    assert observed["state"] == "abstained"
    assert observed["accepted_result_count"] == 0
    assert {row["reason"] for row in observed["claim_decisions"]} == {"unauthorized_at_issue"}


@pytest.mark.parametrize(("case_id", "claim_reasons", "result_reasons"), [
    ("stale-capability", {"expired_capability"}, set()),
    ("claim-race", {"winner", "loser"}, {"accepted"}),
    ("expired-claim", {"expired_claim"}, {"losing_claim"}),
    ("peer-loss", {"unauthorized_device", "winner"}, {"accepted"}),
    ("peer-rejoin", {"expired_capability", "winner"}, {"accepted"}),
    ("cross-session", {"winner"}, {"unknown_claim"}),
    ("unavailable-remote", {"unavailable_capability"}, set()),
    ("result-owner-mismatch", {"winner"}, {"worker_mismatch"}),
    ("three-way-race", {"winner", "loser"}, {"accepted"}),
    ("capability-unavailable-transition", {"unavailable_capability", "winner"}, {"accepted"}),
    ("claim-withdrawal-transition", {"withdrawn", "winner"}, {"accepted"}),
])
def test_fault_reasons_are_explicit(case_id: str, claim_reasons: set[str],
                                    result_reasons: set[str]) -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == case_id)
    observed = baseline.evaluate_case(case, replay_seed=3, replay_count=2)["coordinator"]
    assert {row["reason"] for row in observed["claim_decisions"]} == claim_reasons
    assert {row["reason"] for row in observed["result_decisions"]} == result_reasons


def test_cross_session_result_references_a_real_separate_fixture() -> None:
    case = next(case for case in corpus.load_frozen()["cases"] if case["case_id"] == "cross-session")
    foreign = case["external_reference_records"][0]
    result = next(row for row in case["records"] if row["record_type"] == "result")
    assert foreign["session_id"] != case["session_id"]
    assert foreign["claim_id"] == result["claim_id"]


def test_every_seeded_observation_has_matching_local_capability() -> None:
    for case in corpus.load_frozen()["cases"]:
        observations = [row for row in case["records"] if row["record_type"] == "observation"]
        for observation in observations:
            assert any(
                cap["record_type"] == "capability"
                and cap["producer_device_id"] == observation["producer_device_id"]
                and cap["model_id"] == observation["model_id"]
                and cap["model_version"] == observation["model_version"]
                and cap["artifact_sha256"] == observation["artifact_sha256"]
                and cap["output_schema_version"] == observation["output_schema_version"]
                and cap["status"] == "available"
                and cap["valid_from"] <= observation["created_at"] < cap["expires_at"]
                for cap in case["records"]
            )


def test_run_index_pins_artifact_bytes() -> None:
    index = json.loads((ROOT / "run-index.json").read_text())
    assert index["corpus_sha256"] == corpus.FROZEN_SHA256
    assert index["policy_sha256"] == corpus.POLICY_SHA256
    assert "policy-v1.json" in index["artifacts_sha256"]
    assert "fault-corpus-spec.md" in index["artifacts_sha256"]
    assert "protocol.md" in index["artifacts_sha256"]
    for name, expected in index["artifacts_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
