"""Print per-area status counts from kirocrew-feature-map.md.

    uv run python .kiro/specs/python-factory-bp34j-companion-crew-features/scripts/feature_map_status.py [--rows]

Gate 0 uses this for its row-count report; the owner uses it for "where do we stand".
"""
from __future__ import annotations

import pathlib
import re
import sys

SPEC = pathlib.Path(__file__).resolve().parents[1]
MAP = SPEC / "kirocrew-feature-map.md"
STATUSES = ["PRESENT+WORKS", "PRESENT+BROKEN", "MISSING", "OWNER_NA", "OWNER_DEFERRED", "OWNER_REBRAND", "TODO"]
OUT_OF_M75 = {"OWNER_NA", "OWNER_DEFERRED", "OWNER_REBRAND"}
ROW = re.compile(r"^\| (\d+) \| ([^|]+?) \|.*\| (PRESENT\+WORKS|PRESENT\+BROKEN|MISSING|OWNER_NA|OWNER_DEFERRED|OWNER_REBRAND|TODO) \| [^|]* \|$")


def main() -> None:
    show_rows = "--rows" in sys.argv
    area = None
    per_area: dict[str, dict[str, list[str]]] = {}
    for line in MAP.read_text().splitlines():
        if line.startswith("## "):
            area = line[3:].strip()
            continue
        m = ROW.match(line.strip())
        if m and area:
            per_area.setdefault(area, {s: [] for s in STATUSES})[m.group(3)].append(f"{m.group(1)} {m.group(2).strip()}")

    totals = {s: 0 for s in STATUSES}
    print(f"{'Area':<32} {'works':>5} {'broken':>6} {'missing':>7} {'later':>5} {'n/a':>4} {'todo':>4}  M7.5")
    for name, buckets in per_area.items():
        n = sum(len(v) for v in buckets.values())
        if n == 0:
            continue
        for s in STATUSES:
            totals[s] += len(buckets[s])
        w, b, mi = (len(buckets[s]) for s in ("PRESENT+WORKS", "PRESENT+BROKEN", "MISSING"))
        later = len(buckets["OWNER_DEFERRED"]) + len(buckets["OWNER_REBRAND"])
        na, td = len(buckets["OWNER_NA"]), len(buckets["TODO"])
        scoped = n - later - na
        pct = f"{100 * w // scoped:>3}%" if scoped else "  —"
        print(f"{name:<32} {w:>5} {b:>6} {mi:>7} {later:>5} {na:>4} {td:>4}  {pct}")
        if show_rows:
            for s in ("PRESENT+BROKEN", "MISSING"):
                for r in buckets[s]:
                    print(f"    [{s}] {r}")
    n = sum(totals.values())
    later = totals["OWNER_DEFERRED"] + totals["OWNER_REBRAND"]
    scoped = n - later - totals["OWNER_NA"]
    print("-" * 74)
    print(f"{'TOTAL':<32} {totals['PRESENT+WORKS']:>5} {totals['PRESENT+BROKEN']:>6} {totals['MISSING']:>7} "
          f"{later:>5} {totals['OWNER_NA']:>4} {totals['TODO']:>4}  {100 * totals['PRESENT+WORKS'] // scoped if scoped else 100:>3}%  "
          f"({n} rows; {scoped} in M7.5 scope, {totals['OWNER_REBRAND']} rebrand → M8, {totals['OWNER_DEFERRED']} deferred → M9)")


if __name__ == "__main__":
    main()
