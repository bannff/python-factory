"""Render contracts for the Settings -> Assistant section.

Asserts the security-relevant UI states:
  CONTROL #3: API-key entry field is password-masked; once configured the value
    is NEVER re-rendered (only a '✓ configured' label + Clear).
  CONTROL #5: when no secure keychain exists, an honest message is shown and NO
    entry field is offered.
"""

from __future__ import annotations

import flet as ft

from wall import components as C
from wall.assistant_settings_vm import AssistantSettingsVM


def _walk(control):
    """Yield every control in the tree (depth-first)."""
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        items = child if isinstance(child, list) else [child]
        for c in items:
            if c is not None and hasattr(c, "__class__"):
                yield from _walk(c)


def _password_fields(section) -> list[ft.TextField]:
    return [
        c for c in _walk(section)
        if isinstance(c, ft.TextField) and getattr(c, "password", False)
    ]


def _texts(section) -> list[str]:
    return [c.value for c in _walk(section) if isinstance(c, ft.Text) and c.value]


def _vm(**over) -> AssistantSettingsVM:
    base = dict(
        provider="openai",
        provider_choices=("bedrock", "openai", "anthropic", "gemini", "ollama", "litellm"),
        model_id="gpt-4o",
        model_choices=(("GPT-4o", "gpt-4o"), ("GPT-4o mini (fast)", "gpt-4o-mini")),
        requires_api_key=True,
        has_api_key=False,
        api_key_status="not_set",
        keychain_available=True,
        keychain_message="",
    )
    base.update(over)
    return AssistantSettingsVM(**base)


def _noop(*_a, **_k):
    return None


def _section(vm):
    return C.assistant_settings_section(
        vm, on_provider_change=_noop, on_model_change=_noop,
        on_save_key=_noop, on_clear_key=_noop,
    )


def test_model_dropdown_maps_label_to_id_when_catalog_present():
    vm = _vm(model_choices=(
        ("Claude 3.5 Sonnet v2", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"),
        ("Claude 3.5 Haiku (fast)", "us.anthropic.claude-3-5-haiku-20241022-v1:0"),
    ))
    section = _section(vm)
    dropdowns = [c for c in _walk(section) if isinstance(c, ft.Dropdown)]
    model_dd = [
        d for d in dropdowns
        if any((o.key or "").startswith("us.anthropic") for o in (d.options or []))
    ]
    assert model_dd, "expected a model dropdown when the provider has a catalog"
    # Option key = real model id; visible content = friendly label.
    assert model_dd[0].options[0].key == "us.anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_model_free_text_when_no_catalog():
    vm = _vm(provider="ollama", model_choices=(), requires_api_key=False,
             api_key_status="not_required")
    section = _section(vm)
    fields = [c for c in _walk(section) if isinstance(c, ft.TextField)]
    assert any((f.hint_text or "").find("llama") >= 0 for f in fields), \
        "expected a free-text model field when the provider has no catalog"


def test_not_set_state_renders_masked_password_field():
    section = _section(_vm(api_key_status="not_set"))
    masked = _password_fields(section)
    assert len(masked) == 1
    assert masked[0].password is True
    assert masked[0].can_reveal_password is False


def test_configured_state_never_rerenders_key_and_offers_clear():
    secret = "sk-SUPERSECRET-must-not-appear"
    section = _section(_vm(api_key_status="configured", has_api_key=True))
    # No password entry field once configured.
    assert _password_fields(section) == []
    # The secret value is nowhere in the rendered text (we never had it, but guard anyway).
    assert all(secret not in t for t in _texts(section))
    # A 'configured' affordance is shown.
    assert any("configured" in t.lower() for t in _texts(section))


def test_no_keychain_shows_honest_message_and_no_entry_field():
    section = _section(_vm(
        keychain_available=False,
        keychain_message="No secure keychain available on this device — "
                         "set the key via OPENARCADE_API_KEY env var instead.",
    ))
    # CONTROL #5: no entry field offered.
    assert _password_fields(section) == []
    assert any("No secure keychain" in t for t in _texts(section))


def test_provider_not_requiring_key_shows_not_required():
    section = _section(_vm(provider="bedrock", requires_api_key=False,
                           api_key_status="not_required"))
    assert _password_fields(section) == []
    assert any("Not required" in t for t in _texts(section))
