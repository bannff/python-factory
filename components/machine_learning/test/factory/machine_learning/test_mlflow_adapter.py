"""Tests for MLflow tracker adapter — mlflow module is fully mocked.

No running MLflow server or installed `mlflow` package is required.
Follows the same behavioural surface as ``TestMemoryTracker`` in
``test_runtime.py`` but uses ``unittest.mock.patch`` to inject a
synthetic mlflow module.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from factory.machine_learning.runtime.adapters.mlflow_adapter import MLflowTracker


def _build_mlflow_mock() -> MagicMock:
    """Build a MagicMock that imitates the subset of mlflow we use."""
    mock = MagicMock(name="mlflow")

    # --- experiment handles ---
    exp = MagicMock(name="mlflow.entities.Experiment")
    exp.experiment_id = "exp-1"
    exp.name = "test-exp"
    exp.tags = {"env": "test"}
    mock.get_experiment.return_value = exp
    mock.get_experiment_by_name.return_value = exp
    mock.search_experiments.return_value = [exp]
    mock.create_experiment.return_value = "42"

    # --- run handles ---
    run = MagicMock(name="mlflow.entities.Run")
    run.info.run_id = "run-1"
    run.info.experiment_id = "exp-1"
    run.info.run_name = "test-run"
    run.info.status = "FINISHED"
    run.data.params = {}
    run.data.metrics = {}
    run.data.tags = {}
    mock.get_run.return_value = run
    mock.start_run.return_value = run

    return mock


@pytest.fixture
def mlflow_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a mock mlflow module into sys.modules and return it."""
    mock = _build_mlflow_mock()
    monkeypatch.setitem(sys.modules, "mlflow", mock)
    return mock


class TestMLflowTracker:
    """Tests for the MLflow adapter with mlflow fully mocked."""

    def test_create_experiment(self, mlflow_mock: MagicMock) -> None:
        """create_experiment should return an Experiment with id and name."""
        mlflow_mock.create_experiment.return_value = "42"
        tracker = MLflowTracker()

        exp = tracker.create_experiment("my-exp", description="d", tags={"a": "b"})

        assert exp.id == "42"
        assert exp.name == "my-exp"
        assert exp.description == "d"
        assert exp.tags == {"a": "b"}
        mlflow_mock.create_experiment.assert_called_once_with("my-exp", tags={"a": "b"})

    def test_get_experiment(self, mlflow_mock: MagicMock) -> None:
        """get_experiment should return Experiment when found, None otherwise."""
        tracker = MLflowTracker()

        exp = tracker.get_experiment("exp-1")
        assert exp is not None
        assert exp.id == "exp-1"
        assert exp.name == "test-exp"

        # get_experiment() returns None when mlflow returns None
        mlflow_mock.get_experiment.return_value = None
        assert tracker.get_experiment("missing") is None

    def test_list_experiments(self, mlflow_mock: MagicMock) -> None:
        """list_experiments should return list of Experiment objects."""
        tracker = MLflowTracker()

        exps = tracker.list_experiments()

        assert len(exps) == 1
        assert exps[0].id == "exp-1"
        assert exps[0].name == "test-exp"
        mlflow_mock.search_experiments.assert_called_once()

    def test_start_run(self, mlflow_mock: MagicMock) -> None:
        """start_run should call mlflow.start_run and return a Run."""
        mlflow_mock.start_run.return_value.info.run_id = "new-run-id"
        tracker = MLflowTracker()

        run = tracker.start_run("exp-1", "my-run", tags={"t": "v"})

        assert run.id == "new-run-id"
        assert run.experiment_id == "exp-1"
        assert run.name == "my-run"
        assert run.status == "running"
        assert run.tags == {"t": "v"}
        mlflow_mock.start_run.assert_called_once_with(
            experiment_id="exp-1", run_name="my-run", tags={"t": "v"}
        )

    def test_end_run(self, mlflow_mock: MagicMock) -> None:
        """end_run must pass run_id to mlflow.end_run (Bug B fix)."""
        tracker = MLflowTracker()

        tracker.end_run("run-1", status="completed")

        # The fix: end_run must explicitly target the intended run, not the
        # currently active one. Without run_id, mlflow would end whatever
        # run happened to be active in the thread.
        mlflow_mock.end_run.assert_called_once_with(
            run_id="run-1", status="FINISHED"
        )

    def test_log_param(self, mlflow_mock: MagicMock) -> None:
        """log_param must call mlflow.log_param with run_id (Bug A fix)."""
        tracker = MLflowTracker()

        tracker.log_param("run-1", "lr", 0.01)

        mlflow_mock.log_param.assert_called_once_with("lr", 0.01, run_id="run-1")

    def test_log_params(self, mlflow_mock: MagicMock) -> None:
        """log_params must call mlflow.log_params with run_id (Bug A fix)."""
        tracker = MLflowTracker()

        tracker.log_params("run-1", {"lr": 0.01, "bs": 32})

        mlflow_mock.log_params.assert_called_once_with(
            {"lr": 0.01, "bs": 32}, run_id="run-1"
        )

    def test_log_metric(self, mlflow_mock: MagicMock) -> None:
        """log_metric must call mlflow.log_metric with run_id (Bug A fix)."""
        tracker = MLflowTracker()

        tracker.log_metric("run-1", "loss", 0.5, step=10)

        mlflow_mock.log_metric.assert_called_once_with(
            "loss", 0.5, step=10, run_id="run-1"
        )

    def test_log_metrics(self, mlflow_mock: MagicMock) -> None:
        """log_metrics must call mlflow.log_metrics with run_id (Bug A fix)."""
        tracker = MLflowTracker()

        tracker.log_metrics("run-1", {"a": 0.1, "b": 0.2}, step=5)

        mlflow_mock.log_metrics.assert_called_once_with(
            {"a": 0.1, "b": 0.2}, step=5, run_id="run-1"
        )

    def test_health_check(self, mlflow_mock: MagicMock) -> None:
        """health_check should report healthy when mlflow is importable."""
        tracker = MLflowTracker()

        health = tracker.health_check()

        assert health.healthy is True
        assert health.backend == "mlflow"
        assert health.latency_ms >= 0

    def test_health_check_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """health_check should report unhealthy when mlflow import fails."""
        # Setting sys.modules[name] = None causes import to raise ImportError,
        # matching the real-world "mlflow not installed" case.
        monkeypatch.setitem(sys.modules, "mlflow", None)

        tracker = MLflowTracker()
        health = tracker.health_check()

        assert health.healthy is False
        assert health.backend == "mlflow"
        assert health.message  # error message is populated
