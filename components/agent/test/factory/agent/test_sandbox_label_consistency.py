"""
Label consistency tests for sandbox resource commands.

Verifies:
- SANDBOX_RESOURCE_COMMANDS keys match _GENERATORS keys (minus compat aliases)
- SANDBOX_VALIDATION_COMMANDS has the same keys as SANDBOX_RESOURCE_COMMANDS
"""
from __future__ import annotations

from factory.agent.registry.redteam_sandbox_resources import (
    SANDBOX_RESOURCE_COMMANDS,
    SANDBOX_VALIDATION_COMMANDS,
)
from factory.sandbox.runtime.cfn_defaults import _GENERATORS

# Backward-compat aliases that are intentionally extra in _GENERATORS
_COMPAT_ALIASES = {"DynamoDBTable", "ApiGatewayMethod"}


class TestSandboxLabelConsistency:
    """Labels in resource commands must match CFN generators."""

    def test_resource_commands_match_generators(self) -> None:
        """SANDBOX_RESOURCE_COMMANDS keys == _GENERATORS keys minus aliases."""
        gen_keys = set(_GENERATORS) - _COMPAT_ALIASES
        cmd_keys = set(SANDBOX_RESOURCE_COMMANDS)
        assert cmd_keys == gen_keys, (
            f"extra in commands: {cmd_keys - gen_keys}, "
            f"missing from commands: {gen_keys - cmd_keys}"
        )

    def test_validation_commands_match_resource_commands(self) -> None:
        """SANDBOX_VALIDATION_COMMANDS keys == SANDBOX_RESOURCE_COMMANDS keys."""
        assert set(SANDBOX_VALIDATION_COMMANDS) == set(SANDBOX_RESOURCE_COMMANDS)
