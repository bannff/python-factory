"""Real Companion-X restart acceptance for the CAN/LightGBM passport slice."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from projects.companion_x.api_restart_support import (
    REPO, available_port, brick_call, call, mcp_session, raw_records,
    start_api, stop_api, wait_ready, write_fixture,
)


@pytest.mark.asyncio
async def test_exact_passport_survives_real_api_restart_and_denies_tamper() -> None:
    root = REPO / ".storage/acceptance" / f"sbhyq-8-1-{uuid.uuid4().hex}"
    capture, dbc = write_fixture(root)
    port = available_port()
    first, first_log = start_api(root, port, 1)
    try:
        await wait_ready(first, port, root / "api-1.log")
        async with mcp_session(port) as session:
            listed = await call(session, "list_bricks")
            names = {item["name"] for item in listed["bricks"]}
            assert {"dataset", "machine_learning"} <= names
            for brick in ("dataset", "machine_learning"):
                discovered = await call(
                    session, "get_brick_tools", {"brick_name": brick},
                )
                assert discovered["brick"] == brick and discovered["count"] > 0
            pipeline_envelope = await brick_call(session, "can_run_full_pipeline", {
                "mf4_dir": str(capture), "dbc_path": str(dbc),
                "vehicle_id": "restart-fixture", "storage_root": str(root / "datasets"),
                "max_samples": 80, "top_n_can_ids": 1, "model_types": ["lightgbm"],
                "config_overrides": {
                    "synthesize": {"multiplier": 3, "failure_rate": 0.3, "seed": 7,
                                   "onset_frames": 0, "decay_frames": 0},
                    "window": {"window_size_ms": 100, "step_size_ms": 50,
                               "grid_resolution_ms": 10, "observation_cutoff_ms": 100,
                               "label_horizon_ms": 20},
                    "augment": {"techniques": ["jitter"], "seed": 7},
                },
            })
            assert pipeline_envelope["ok"], pipeline_envelope
            pipeline = pipeline_envelope["data"]
            row = pipeline["comparison_table"][0]
            assert row.get("passport_status") == "published", row.get("error", row)
            candidate_ref = row["passport_ref"]
            promoted_envelope = await brick_call(
                session, "ml_verify_and_promote_lightgbm_passport", {
                    "model_id": candidate_ref["model_id"],
                    "model_version": candidate_ref["model_version"],
                    "passport_revision": candidate_ref["passport_revision"],
                    "passport_uri": candidate_ref["uri"],
                    "passport_digest": candidate_ref["digest"],
                },
            )
            assert promoted_envelope["ok"], promoted_envelope
            promoted = promoted_envelope["data"]
            assert promoted["status"] == "published", promoted
            exact_ref = promoted["ref"]
            assert exact_ref["passport_revision"] == 2
            model_id, contract_digest = row["model_id"], row["contract_digest"]
            model_path = Path(row["model_path"])
        first_pid = first.pid
    finally:
        stop_api(first, first_log)

    second, second_log = start_api(root, port, 2)
    try:
        assert second.pid != first_pid
        await wait_ready(second, port, root / "api-2.log")
        async with mcp_session(port) as session:
            await call(session, "get_brick_tools", {"brick_name": "machine_learning"})
            warm = await brick_call(session, "can_get_model_info", {"model_id": model_id})
            assert warm["ok"] and not warm["data"]["found"]
            prediction_args = {
                "records": raw_records(), "contract_digest": contract_digest,
                "model_id": exact_ref["model_id"],
                "model_version": exact_ref["model_version"],
                "passport_revision": exact_ref["passport_revision"],
                "passport_uri": exact_ref["uri"], "passport_digest": exact_ref["digest"],
            }
            predicted = await brick_call(session, "can_predict_failure", prediction_args)
            assert predicted["ok"] and predicted["data"]["status"] == "ok", predicted
            mlmodel = model_path / "MLmodel"
            mlmodel.write_text(mlmodel.read_text() + "\n# tampered\n")
            denied = await brick_call(session, "can_predict_failure", prediction_args)
            assert not denied["ok"] and denied["data"] is None
            assert "failed retrieval or verification" in denied["error"]
    finally:
        stop_api(second, second_log)
