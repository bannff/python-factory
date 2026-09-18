"""Apply owner rulings of 2026-09-14 12:39 to kirocrew-feature-map.md.

Sets Status + Evidence on specific rows. Idempotent. Owner words quoted verbatim
because OWNER_* statuses are only valid in the owner's words.

    uv run python .kiro/specs/python-factory-bp34j-companion-crew-features/scripts/apply_owner_rulings_20260914.py
"""
from __future__ import annotations

import pathlib
import re

SPEC = pathlib.Path(__file__).resolve().parents[1]
MAP = SPEC / "kirocrew-feature-map.md"

DEFERRED_FEATURE = ("OWNER_DEFERRED", 'Owner 2026-09-14 12:39: "we can defer voice/channels (i want these but we can put these at the back since they\'re features)". Build in M9 Deferred features.')
DEFERRED_REMOTE = ("OWNER_DEFERRED", 'Owner 2026-09-14 12:39: "remotecrew/webhooks sound super interesting but not core. Defer like features (e.g. slack etc)". Build in M9 Deferred features.')
DEFERRED_APPS = ("OWNER_DEFERRED", 'Owner 2026-09-14 12:39: "i dont need an app store, we can have a \'brick store\' and defer this to later". Re-spec as Brick Store in M9 Deferred features.')
REBRAND_REDIRECT = ("OWNER_REBRAND", 'Owner 2026-09-14 12:39: "old kirocrew urls wont work because im making this my own thing. I\'ll eventually point to my own github and other shit (even rebrand). So we can rebrand/whatever last but before the deferred features". Handle in M8 Rebrand.')
REBRAND_OPERATOR = ("OWNER_REBRAND", 'Owner 2026-09-14 12:39: "standalone operator surface - sounds like marketing shit we dont need that i can either ditch or set as \'needs to be rebranded\' and deferred before the last features". Decide ditch-vs-rebrand per row in M8 Rebrand.')

RULINGS: dict[int, tuple[str, str]] = {}
RULINGS.update({87: DEFERRED_FEATURE, 91: DEFERRED_FEATURE})              # voice, channels
RULINGS.update({94: DEFERRED_REMOTE, 95: DEFERRED_REMOTE, 116: DEFERRED_REMOTE})  # webhooks, instances/Remote Crew, standalone Webhooks
RULINGS.update({n: DEFERRED_APPS for n in range(69, 77)})                # Apps 69-76
RULINGS.update({n: REBRAND_REDIRECT for n in range(132, 141)})           # Redirects 132-140
RULINGS.update({n: REBRAND_OPERATOR for n in (117, 118, 119, 120, 121, 122, 123)})  # operator surfaces

# Explicit KEEP-CORE confirmations (status untouched; Evidence gets the owner's words so nobody re-asks)
CORE_NOTE = {
    93: 'Owner 2026-09-14 12:39: "computer use --> CORE, agents are worthless if they can\'t do shit for me".',
    92: 'Owner 2026-09-14 12:39: "browser - core, how else do i configure the agents".',
    100: 'Owner 2026-09-14 12:39: "release sounds core - not sure wtf this does but sounds key". (Release channel/update check/changelog — re-spec against Companion-X\'s own release story.)',
    98: 'Owner 2026-09-14 12:39: "secrets management page sounds core too, nice way to manage secrets".',
}

ROW = re.compile(r"^(\| (\d+) \| .*?\| [^|]*\| )([^|]+?)( \| )([^|]*)( \|)$")


def main() -> None:
    out: list[str] = []
    changed = 0
    for line in MAP.read_text().splitlines():
        m = ROW.match(line)
        if m:
            n = int(m.group(2))
            if n in RULINGS:
                status, evidence = RULINGS[n]
                new = f"{m.group(1)}{status}{m.group(4)}{evidence}{m.group(6)}"
                if new != line:
                    changed += 1
                line = new
            elif n in CORE_NOTE and CORE_NOTE[n] not in line:
                ev = (m.group(5).strip() + " " if m.group(5).strip() else "") + CORE_NOTE[n]
                line = f"{m.group(1)}{m.group(3)}{m.group(4)}{ev}{m.group(6)}"
                changed += 1
        out.append(line)
    MAP.write_text("\n".join(out) + "\n")
    print(f"rulings applied: {changed} rows changed ({len(RULINGS)} deferred/rebrand, {len(CORE_NOTE)} core notes)")


if __name__ == "__main__":
    main()
