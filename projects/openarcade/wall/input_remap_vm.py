"""Pure view-model mapper for the Input Remap screen. Zero Flet imports."""

from __future__ import annotations

from dataclasses import dataclass

from factory.arcade_config.runtime.models import RETROPAD_BUTTONS, InputRemap
from factory.arcade_config.runtime.input_remaps import RETROPAD_BUTTON_ORDER


@dataclass(frozen=True)
class InputRemapRow:
    """Presentation-ready row for a single button remap (always editable)."""

    button: str
    label: str  # humanised button name
    current_target: str
    choices: tuple[str, ...]  # all valid targets (= RETROPAD_BUTTON_ORDER)


@dataclass(frozen=True)
class InputRemapVM:
    """Complete view-model for the Controller Mapping section."""

    rows: tuple[InputRemapRow, ...]


def _humanize_button(btn: str) -> str:
    """Best-effort label from a RetroPad button name."""
    return btn.upper().replace("_", " ")


def input_remap_vm_from_remaps(remaps: list[InputRemap]) -> InputRemapVM:
    """Build the presentation VM from domain InputRemap objects.

    Every row is editable — choices = all canonical RetroPad buttons.
    """
    rows: list[InputRemapRow] = []
    for remap in remaps:
        rows.append(InputRemapRow(
            button=remap.retropad_button,
            label=_humanize_button(remap.retropad_button),
            current_target=remap.target,
            choices=RETROPAD_BUTTON_ORDER,
        ))
    return InputRemapVM(rows=tuple(rows))
