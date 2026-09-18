"""Pure shader picker VM. Zero IO, zero Flet.

Builds choices + current value for the shader dropdown.
Mirrors dge52's append-live-value degradation pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

from factory.arcade_config.interface import SHADER_PRESETS


@dataclass(frozen=True)
class ShaderPickerVM:
    """Presentation-ready data for the shader dropdown row."""

    current: str
    choices: tuple[str, ...]


def build_shader_picker_vm(
    shader_enabled: bool,
    shader_name: str,
) -> ShaderPickerVM:
    """Build the shader picker VM from resolved runtime state.

    Rules:
    - If shader is disabled or shader_name is empty -> current = "None".
    - If shader_name is NOT in SHADER_PRESETS -> APPEND it (never lose real state).
    - Otherwise use the shader_name as current.
    """
    if not shader_enabled or not shader_name:
        current = "None"
    else:
        current = shader_name

    choices = SHADER_PRESETS
    if current != "None" and current not in choices:
        # Disk is truth — append the live value (dge52 degradation pattern)
        choices = (*choices, current)

    return ShaderPickerVM(current=current, choices=choices)
