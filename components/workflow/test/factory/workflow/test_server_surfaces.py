"""Module-level workflow contract surfaces delegate to the runtime."""
import logging
from unittest.mock import MagicMock

from factory.workflow import server


def test_module_surfaces_delegate_without_false_backend_claims(monkeypatch):
    runtime = MagicMock()
    runtime.get_capabilities.return_value = {
        "feature_flags": {"durable_named_mcp_execution": "sqlite-only"},
    }
    runtime.health_check.return_value = {
        "status": "ok", "storage": {"backend": "sqlite"},
        "durable_named_mcp_ready": True,
    }
    runtime.describe_config_schema.return_value = {"settings_schema": {}}
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)

    capabilities = server.get_capabilities()
    health = server.health_check()
    assert capabilities["feature_flags"]["durable_named_mcp_execution"] == "sqlite-only"
    assert health["storage"]["backend"] == "sqlite"
    assert server.describe_config_schema() == {"settings_schema": {}}
    runtime.get_capabilities.assert_called_once_with()
    runtime.health_check.assert_called_once_with()


def test_missing_settings_yaml_logs_actionable_warning_and_still_starts(
    monkeypatch, tmp_path, caplog,
):
    """A bad WORKFLOW_CONFIG_DIR must be visible, not a healthy empty server."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("WORKFLOW_CONFIG_DIR", str(config_dir))

    with caplog.at_level(logging.WARNING):
        runtime = server.get_runtime()

    assert runtime.executor.backend_name == "local"
    assert runtime.storage.health_check()["ok"] is True
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert warnings, "missing settings.yaml must warn instead of passing silently"
    assert any(
        "WORKFLOW_CONFIG_DIR" in message
        and str((config_dir / "settings.yaml").resolve()) in message
        for message in warnings
    ), warnings


def test_unconfigured_config_dir_is_reported_in_module_surfaces(
    monkeypatch, tmp_path, caplog,
):
    config_dir = tmp_path / "config"
    monkeypatch.setenv("WORKFLOW_CONFIG_DIR", str(config_dir))
    expected_missing = str((config_dir / "settings.yaml").resolve())

    with caplog.at_level(logging.WARNING):
        health = server.health_check()
        capabilities = server.get_capabilities()

    assert health["config"]["configured"] is False
    assert health["config"]["missing"] == expected_missing
    assert capabilities["config"]["configured"] is False
    assert capabilities["config"]["missing"] == expected_missing
