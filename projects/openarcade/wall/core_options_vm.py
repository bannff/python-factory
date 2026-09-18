"""Pure view-model mapper for the Core Options screen. Zero Flet imports."""

from __future__ import annotations

from dataclasses import dataclass

from factory.arcade_config.runtime.models import CoreOption, RawOption
from factory.arcade_config.runtime.schemas import CORE_OPTION_SCHEMAS


@dataclass(frozen=True)
class CoreOptionRow:
    """Presentation-ready row for a single curated core option."""

    key: str
    label: str
    value: str
    choices: tuple[str, ...]
    editable: bool  # always True for curated


@dataclass(frozen=True)
class RawOptionRow:
    """Presentation-ready row for an uncurated option (read-only)."""

    key: str
    label: str  # derived from key (strip prefix, titlecase)
    value: str
    editable: bool  # always False


@dataclass(frozen=True)
class CoreOptionsVM:
    """Complete view-model for the Core Options screen."""

    curated: tuple[CoreOptionRow, ...]
    uncurated: tuple[RawOptionRow, ...]


def _humanize_key(key: str) -> str:
    """Best-effort label from an option key: strip known prefixes, replace _ with space, titlecase."""
    for prefix in ("snes9x_", "mgba_", "mupen64_", "mame_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    return key.replace("_", " ").strip().title()


def core_options_vm_from_options(
    curated: list[CoreOption],
    raw: list[RawOption],
    schema: dict[str, tuple[str, tuple[str, ...]]] | None = None,
) -> CoreOptionsVM:
    """Build the presentation VM from domain objects.

    Uses schema for human labels when available; falls back to _humanize_key.
    """
    schema = schema or {}

    curated_rows: list[CoreOptionRow] = []
    for opt in curated:
        label_info = schema.get(opt.key)
        label = label_info[0] if label_info else _humanize_key(opt.key)
        curated_rows.append(CoreOptionRow(
            key=opt.key,
            label=label,
            value=opt.value,
            choices=opt.allowed,
            editable=True,
        ))

    raw_rows: list[RawOptionRow] = []
    for opt in raw:
        raw_rows.append(RawOptionRow(
            key=opt.key,
            label=_humanize_key(opt.key),
            value=opt.value,
            editable=False,
        ))

    return CoreOptionsVM(
        curated=tuple(curated_rows),
        uncurated=tuple(raw_rows),
    )
