"""Module-level workflow contract surfaces delegate to the runtime."""
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
