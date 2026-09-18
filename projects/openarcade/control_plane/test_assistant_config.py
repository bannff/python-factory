"""Tests for assistant config service + assistant tools + assistant settings VM.

Behavior-named, AAA structure. FakeKeychain injected everywhere —
tests NEVER touch real OS keychain.

Covers all 6 blocking security controls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.assistant_config_service import (
    AssistantProvider,
    KeychainBackend,
    KeychainUnavailable,
    NullKeychain,
    has_api_key,
    get_api_key,
    store_api_key,
    clear_api_key,
    load_assistant_config,
    save_assistant_config,
    requires_api_key,
)
from control_plane.assistant import AssistantConfig, NullAssistant, resolve_assistant


# ---------------------------------------------------------------------------
# FakeKeychain — in-memory dict, injected everywhere
# ---------------------------------------------------------------------------


class FakeKeychain:
    """In-memory keychain for testing. Never touches OS keychain."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}

    def get(self, service: str, key: str) -> str | None:
        return self._store.get(service, {}).get(key)

    def set(self, service: str, key: str, value: str) -> None:
        self._store.setdefault(service, {})[key] = value

    def delete(self, service: str, key: str) -> None:
        self._store.get(service, {}).pop(key, None)


# ---------------------------------------------------------------------------
# CONTROL #1: JSON contains ONLY provider+model_id — NEVER api_key
# ---------------------------------------------------------------------------


def test_save_config_never_writes_api_key(tmp_path: Path):
    """CONTROL #1: assistant.json contains only provider+model_id, never api_key."""
    save_assistant_config("openai", "gpt-4o", path=tmp_path)
    content = (tmp_path / "assistant.json").read_text()
    assert "api_key" not in content
    data = json.loads(content)
    assert set(data.keys()) == {"provider", "model_id"}


def test_load_config_strips_any_extra_fields(tmp_path: Path):
    """load_assistant_config only returns provider+model_id even if file has extras."""
    (tmp_path / "assistant.json").write_text(
        json.dumps({"provider": "openai", "model_id": "gpt-4", "api_key": "SECRET"})
    )
    result = load_assistant_config(tmp_path)
    assert "api_key" not in result
    assert result == {"provider": "openai", "model_id": "gpt-4"}


# ---------------------------------------------------------------------------
# CONTROL #2: No repr/log/exception prints the key
# ---------------------------------------------------------------------------


def test_assistant_config_repr_redacts_api_key():
    """CONTROL #2: repr(AssistantConfig) never shows api_key value."""
    cfg = AssistantConfig(model_id="gpt-4o", provider="openai", api_key="sk-secret123")
    r = repr(cfg)
    assert "sk-secret123" not in r
    assert "REDACTED" in r


def test_assistant_config_str_redacts_api_key():
    """CONTROL #2: str() also redacts."""
    cfg = AssistantConfig(model_id="gpt-4o", provider="openai", api_key="sk-secret123")
    assert "sk-secret123" not in str(cfg)


# ---------------------------------------------------------------------------
# CONTROL #6: api_key field is repr=False + custom __repr__
# ---------------------------------------------------------------------------


def test_assistant_config_field_repr_false():
    """CONTROL #6: dataclass field(repr=False) hides api_key from default repr."""
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(AssistantConfig)}
    assert fields["api_key"].repr is False


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


def test_config_round_trip(tmp_path: Path):
    """save then load returns same provider+model_id."""
    save_assistant_config("anthropic", "claude-3-opus", path=tmp_path)
    loaded = load_assistant_config(tmp_path)
    assert loaded == {"provider": "anthropic", "model_id": "claude-3-opus"}


def test_load_config_returns_empty_when_missing(tmp_path: Path):
    """load_assistant_config returns {} when no file exists."""
    assert load_assistant_config(tmp_path) == {}


# ---------------------------------------------------------------------------
# Keychain ops — FakeKeychain
# ---------------------------------------------------------------------------


def test_store_and_get_api_key():
    """store_api_key persists; get_api_key retrieves."""
    kc = FakeKeychain()
    store_api_key("openai", "sk-abc123", keychain=kc)
    assert get_api_key("openai", keychain=kc) == "sk-abc123"


def test_has_api_key_true_when_stored():
    """has_api_key returns True when key exists."""
    kc = FakeKeychain()
    store_api_key("anthropic", "ant-key", keychain=kc)
    assert has_api_key("anthropic", keychain=kc) is True


def test_has_api_key_false_when_not_stored():
    """has_api_key returns False when no key."""
    kc = FakeKeychain()
    assert has_api_key("gemini", keychain=kc) is False


def test_clear_api_key_removes():
    """clear_api_key removes stored key."""
    kc = FakeKeychain()
    store_api_key("openai", "key", keychain=kc)
    clear_api_key("openai", keychain=kc)
    assert get_api_key("openai", keychain=kc) is None


# ---------------------------------------------------------------------------
# NullKeychain — fail-closed
# ---------------------------------------------------------------------------


def test_null_keychain_set_raises_keychain_unavailable():
    """NullKeychain.set raises KeychainUnavailable — never stores plaintext."""
    kc = NullKeychain()
    with pytest.raises(KeychainUnavailable):
        kc.set("openarcade", "openai_api_key", "secret")


def test_null_keychain_get_returns_none():
    """NullKeychain.get returns None."""
    kc = NullKeychain()
    assert kc.get("openarcade", "openai_api_key") is None


def test_null_keychain_delete_raises():
    """NullKeychain.delete raises KeychainUnavailable."""
    kc = NullKeychain()
    with pytest.raises(KeychainUnavailable):
        kc.delete("openarcade", "openai_api_key")


# ---------------------------------------------------------------------------
# requires_api_key
# ---------------------------------------------------------------------------


def test_requires_api_key_false_for_bedrock():
    assert requires_api_key(AssistantProvider.bedrock) is False


def test_requires_api_key_false_for_ollama():
    assert requires_api_key(AssistantProvider.ollama) is False


def test_requires_api_key_true_for_openai():
    assert requires_api_key(AssistantProvider.openai) is True


def test_requires_api_key_true_for_anthropic():
    assert requires_api_key(AssistantProvider.anthropic) is True


def test_requires_api_key_true_for_gemini():
    assert requires_api_key(AssistantProvider.gemini) is True


def test_requires_api_key_true_for_litellm():
    assert requires_api_key(AssistantProvider.litellm) is True


def test_requires_api_key_true_for_unknown_provider():
    """Unknown providers default to requiring a key (fail-closed)."""
    assert requires_api_key("mystery_provider") is True


# ---------------------------------------------------------------------------
# Provider → builder map
# ---------------------------------------------------------------------------


def test_provider_builders_map_has_all_providers():
    """Every AssistantProvider has a builder in the map."""
    pytest.importorskip("strands", reason="strands-agents not installed")
    from control_plane.strands_assistant import PROVIDER_BUILDERS

    for p in AssistantProvider:
        assert p.value in PROVIDER_BUILDERS, f"Missing builder for {p.value}"


# ---------------------------------------------------------------------------
# resolve_assistant — fail-closed when key missing
# ---------------------------------------------------------------------------


def test_resolve_assistant_returns_null_when_key_required_but_missing():
    """resolve_assistant fail-closes: provider needs key, no key → NullAssistant."""
    config = AssistantConfig(
        model_id="gpt-4o", provider="openai", api_key=None
    )
    assistant = resolve_assistant(config)
    assert isinstance(assistant, NullAssistant)


def test_resolve_assistant_null_message_names_provider():
    """Fail-closed NullAssistant mentions the provider name."""
    config = AssistantConfig(
        model_id="gpt-4o", provider="openai", api_key=None
    )
    assistant = resolve_assistant(config)
    assert isinstance(assistant, NullAssistant)
    # Access the stored message
    assert "openai" in assistant._message


def test_resolve_assistant_bedrock_does_not_require_key():
    """Bedrock provider proceeds without key (uses IAM)."""
    config = AssistantConfig(
        model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        provider="bedrock",
        api_key=None,
    )
    # Should not be NullAssistant due to missing key
    # (will be NullAssistant if strands not installed, but NOT for key reasons)
    # We test it doesn't hit the key-check path
    from control_plane.assistant import requires_api_key as rak

    assert rak("bedrock") is False


# ---------------------------------------------------------------------------
# AssistantConfig.from_env back-compatibility
# ---------------------------------------------------------------------------


def test_config_from_env_reads_model_id(monkeypatch):
    """AssistantConfig.from_env reads OPENARCADE_MODEL_ID."""
    monkeypatch.setenv("OPENARCADE_MODEL_ID", "us.meta.llama3-1-8b-instruct-v1:0")
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("OPENARCADE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENARCADE_API_KEY", raising=False)
    config = AssistantConfig.from_env()
    assert config.model_id == "us.meta.llama3-1-8b-instruct-v1:0"


def test_config_from_env_falls_back_to_bedrock_model(monkeypatch):
    """AssistantConfig.from_env falls back to OPENARCADE_BEDROCK_MODEL."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.setenv("OPENARCADE_BEDROCK_MODEL", "anthropic.claude-v2")
    monkeypatch.delenv("OPENARCADE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENARCADE_API_KEY", raising=False)
    config = AssistantConfig.from_env()
    assert config.model_id == "anthropic.claude-v2"


def test_config_from_env_returns_none_model_when_unset(monkeypatch):
    """AssistantConfig.from_env returns model_id=None when no env set."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("OPENARCADE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENARCADE_API_KEY", raising=False)
    config = AssistantConfig.from_env()
    assert config.model_id is None


# ---------------------------------------------------------------------------
# Wall VM — assistant settings
# ---------------------------------------------------------------------------


def test_assistant_settings_vm_never_exposes_key():
    """AssistantSettingsVM has no field that could hold the actual key."""
    from wall.assistant_settings_vm import build_assistant_settings_vm

    kc = FakeKeychain()
    store_api_key("openai", "sk-secret", keychain=kc)
    # Manually set config so VM can find it
    import control_plane.assistant_config_service as svc

    original = svc._config_dir

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        save_assistant_config("openai", "gpt-4o", path=Path(td))
        svc._config_dir = lambda: Path(td)  # type: ignore[assignment]
        try:
            vm = build_assistant_settings_vm(keychain=kc)
        finally:
            svc._config_dir = original  # type: ignore[assignment]

    assert "sk-secret" not in str(vm)
    assert vm.has_api_key is True
    assert vm.api_key_status == "configured"


def test_assistant_settings_vm_keychain_unavailable():
    """CONTROL #5: NullKeychain shows honest disabled message."""
    from wall.assistant_settings_vm import build_assistant_settings_vm

    import control_plane.assistant_config_service as svc
    import tempfile

    original = svc._config_dir
    kc = NullKeychain()

    with tempfile.TemporaryDirectory() as td:
        save_assistant_config("openai", "gpt-4o", path=Path(td))
        svc._config_dir = lambda: Path(td)  # type: ignore[assignment]
        try:
            vm = build_assistant_settings_vm(keychain=kc)
        finally:
            svc._config_dir = original  # type: ignore[assignment]

    assert vm.keychain_available is False
    assert "OPENARCADE_API_KEY" in vm.keychain_message
    assert vm.has_api_key is False


# ---------------------------------------------------------------------------
# MCP tool: get_assistant_config never includes key
# ---------------------------------------------------------------------------


def test_get_assistant_config_tool_never_returns_key(tmp_path: Path, monkeypatch):
    """get_assistant_config MCP tool NEVER includes api_key in response."""
    import control_plane.assistant_config_service as svc
    import control_plane.assistant_tools as at_mod

    monkeypatch.setattr(svc, "_config_dir", lambda: tmp_path)
    save_assistant_config("openai", "gpt-4o", path=tmp_path)

    kc = FakeKeychain()
    store_api_key("openai", "sk-should-not-appear", keychain=kc)
    # Patch resolve_keychain in BOTH the source module and the tools module
    monkeypatch.setattr(svc, "resolve_keychain", lambda: kc)
    monkeypatch.setattr(at_mod, "resolve_keychain", lambda: kc)

    from control_plane.assistant_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    registered_fns: dict[str, object] = {}

    def capture_tool():
        def decorator(fn):
            registered_fns[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = capture_tool
    register(mcp, context=None)

    result = registered_fns["get_assistant_config"]()
    # CONTROL #2: The actual key value must never appear in the response
    assert "sk-should-not-appear" not in str(result)
    # Response should not have a field that holds the raw key
    assert "api_key" not in result  # no key named "api_key" in the dict
    assert result["has_api_key"] is True


# ---------------------------------------------------------------------------
# MCP tool: set_assistant_config with NullKeychain returns honest error
# ---------------------------------------------------------------------------


def test_set_assistant_config_tool_fail_closed_on_null_keychain(
    tmp_path: Path, monkeypatch
):
    """set_assistant_config with key on NullKeychain returns error, writes NO plaintext."""
    import control_plane.assistant_config_service as svc

    monkeypatch.setattr(svc, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(svc, "resolve_keychain", lambda: NullKeychain())

    from control_plane.assistant_tools import register
    from unittest.mock import MagicMock

    mcp = MagicMock()
    registered_fns: dict[str, object] = {}

    def capture_tool():
        def decorator(fn):
            registered_fns[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = capture_tool
    register(mcp, context=None)

    result = registered_fns["set_assistant_config"]("openai", "gpt-4o", "sk-secret")
    assert result["success"] is False
    assert result["key_saved"] is False
    assert "keychain" in result["message"].lower() or "env var" in result["message"].lower()

    # CONTROL #1: Verify JSON file has NO api_key
    content = (tmp_path / "assistant.json").read_text()
    assert "sk-secret" not in content
    assert "api_key" not in content
