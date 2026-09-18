"""Real two-PID MCP restart acceptance for Dataset -> LNN and Chronos2."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import stat
import uuid

import numpy as np
import pytest

from projects.companion_x.api_restart_support import (
    REPO, available_port, call, call_brick, mcp_session,
    start_api, stop_api, wait_ready,
)
from projects.companion_x.can_native_restart_fixture import (
    sealed_chronos_config, write_can_fixture,
)
from projects.companion_x.can_native_restart_flow import (
    dataset_request, discover, select_pattern, train_and_promote,
)


@contextmanager
def _tampered(path: Path):
    original, mode = path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | stat.S_IWUSR)
    try:
        path.write_bytes(original + b"tamper")
        yield
    finally:
        path.write_bytes(original)
        path.chmod(mode)


async def _score(session, case):
    return await call_brick(
        session, "machine_learning", "ml_predict_neural_passport",
        case["score_args"],
    )


async def _assert_tamper_denied(session, case) -> None:
    denied = await _score(session, case)
    assert not denied["ok"] and denied["data"] is None


async def _survives(session) -> None:
    envelope = await call(session, "get_brick_tools", {"brick_name": "machine_learning"})
    assert envelope["ok"], envelope
    assert envelope["data"]["count"] > 0


@pytest.mark.asyncio
async def test_lnn_chronos_generated_can_survive_restart_and_tamper() -> None:
    root = REPO / ".storage/acceptance" / f"sbhyq-12-1-{uuid.uuid4().hex}"
    capture, catalog_entry = write_can_fixture(root)
    chronos_config = sealed_chronos_config(root / "passports")
    port = available_port()
    first, first_log = start_api(root, port, 1)
    try:
        await wait_ready(first, port, root / "api-1.log")
        async with mcp_session(port) as session:
            await discover(session)
            pattern = await select_pattern(
                session, catalog_entry["message_fingerprints"],
            )
            request = dataset_request(root, capture, pattern)
            terminal_envelope = await call_brick(
                session, "dataset", "dataset_materialize_can_training_bundle", request,
            )
            assert terminal_envelope["ok"], terminal_envelope
            terminal = terminal_envelope["data"]
            assert terminal["status"] == "completed", terminal
            assert terminal["dbc_selection"]["message_fingerprints"] \
                == catalog_entry["message_fingerprints"]
            refs = terminal["training_bundle"]["training_artifacts_by_can_id"]
            assert refs and all(
                {"contract", "x_3d", "y", "timespans"} <= set(value)
                for value in refs.values()
            )
            lnn = await train_and_promote(
                session, family="lnn", request=request,
            )
            chronos = await train_and_promote(
                session, family="chronos", request=request,
                model_config=chronos_config,
            )
            assert not list((root / "passports/models/lightgbm").glob("**/*"))
            first_pid = first.pid
    finally:
        stop_api(first, first_log)

    second, second_log = start_api(root, port, 2)
    try:
        assert second.pid != first_pid
        await wait_ready(second, port, root / "api-2.log")
        async with mcp_session(port) as session:
            await discover(session)
            for case in (lnn, chronos):
                warm = await call_brick(session, "machine_learning", "can_get_model_info", {
                    "model_id": case["passport_ref"]["model_id"],
                })
                assert warm["ok"] and not warm["data"]["found"]
                cold_envelope = await _score(session, case)
                assert cold_envelope["ok"], cold_envelope
                cold = cold_envelope["data"]
                assert cold["status"] == "completed", cold
                expected = np.asarray(case["warm_score"]["y_score"], dtype=float)
                actual = np.asarray(cold["y_score"], dtype=float)
                assert cold["count"] == len(expected) == len(actual) > 0
                assert np.isfinite(actual).all()
                np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7)

            lnn_model = Path(lnn["row"]["model_path"])
            with _tampered(lnn_model):
                await _assert_tamper_denied(session, lnn)
            recovered = await _score(session, lnn)
            assert recovered["ok"] and recovered["data"]["status"] == "completed"
            await _survives(session)

            timing = Path(lnn["score_args"]["live_timing_uri"].removeprefix("file://"))
            with _tampered(timing):
                await _assert_tamper_denied(session, lnn)
            recovered = await _score(session, lnn)
            assert recovered["ok"] and recovered["data"]["status"] == "completed"
            await _survives(session)

            chronos_root = Path(chronos["row"]["model_path"])
            with _tampered(chronos_root / "backbone" / "model.safetensors"):
                await _assert_tamper_denied(session, chronos)
            recovered = await _score(session, chronos)
            assert recovered["ok"] and recovered["data"]["status"] == "completed"
            await _survives(session)

            passport = Path(chronos["passport_ref"]["uri"].removeprefix("file://"))
            with _tampered(passport):
                await _assert_tamper_denied(session, chronos)
            recovered = await _score(session, chronos)
            assert recovered["ok"] and recovered["data"]["status"] == "completed"
            await _survives(session)
    finally:
        stop_api(second, second_log)
