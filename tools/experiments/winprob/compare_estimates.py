"""What changes between two WPA estimate files: numbers, flags, claims and what would be imported.

    uv run python tools/experiments/winprob/compare_estimates.py <a.json> <b.json>

The choice per (champion, role, slot) is the core's rule (app/core select.rs `choose`): the most
played option (`chosen`, ties to the smallest id) unless a claimable option compared head to
head with it is clear (no `no_clear_difference`, contrast > 0) or has a shrunk contrast of at
least BEST_BET_MIN; the largest shrunk gain wins, labelled clearly better when clear. Slot by
slot: the app builds rune pages and item sections from these, which this doesn't redo.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

TAU, BEST_BET_MIN = 0.02, 0.005
"""As in the core (select.rs)."""

type Row = dict[str, Any]
type Option = tuple[str, str, int, str]
type Slot = tuple[str, str, int]
type Choice = tuple[str, str]
"""(option, label): label is popular, best_bet or clearly_better."""


def load(path: Path) -> dict[Option, Row]:
    rows: list[Row] = json.loads(path.read_text())["estimates"]
    return {(r["champion"], r["role"], r["slot"], r["option"]): r for r in rows}


def shrunk(wpa: float, ci: list[float] | None) -> float | None:
    if ci is None:
        return None
    se = abs(ci[1] - ci[0]) / (2 * 1.96)
    return wpa * TAU**2 / (TAU**2 + se**2)


def _claimable(r: Row) -> bool:
    return r["wpa"] is not None and not ({"low_sample", "low_overlap"} & set(r["flags"]))


def _id(option: str) -> tuple[int, int | str]:
    return (0, int(option)) if option.lstrip("-").isdigit() else (1, option)


def _bet(r: Row, popular: str) -> tuple[float, bool] | None:
    """Its shrunk gain and whether it's clear, when it may be the best bet against `popular`."""
    if r["versus"] != popular or r["contrast"] is None or not _claimable(r):
        return None
    clear = "no_clear_difference" not in r["flags"] and r["contrast"] > 0
    gain = shrunk(r["contrast"], r["contrast_ci"])
    if gain is None:
        gain = r["contrast"] if clear else None
    if gain is None or not (clear or gain >= BEST_BET_MIN):
        return None
    return gain, clear


def choose(rows: list[Row]) -> Choice:
    popular = min(rows, key=lambda r: (-(r.get("chosen") or r["n"]), _id(r["option"])))
    best: tuple[Row, float, bool] | None = None
    for r in rows:
        bet = None if r is popular else _bet(r, popular["option"])
        if bet is None:
            continue
        better = best is None or bet[0] > best[1]
        tied_lower = (
            best is not None and bet[0] == best[1] and _id(r["option"]) < _id(best[0]["option"])
        )
        if better or tied_lower:
            best = (r, *bet)
    if best is None:
        return popular["option"], "popular"
    return best[0]["option"], "clearly_better" if best[2] else "best_bet"


def choices(estimates: dict[Option, Row]) -> dict[Slot, Choice]:
    slots: dict[Slot, list[Row]] = defaultdict(list)
    for (champion, role, slot, _), r in estimates.items():
        slots[(champion, role, slot)].append(r)
    return {k: choose(rows) for k, rows in slots.items()}


def _gaps(a: dict[Option, Row], b: dict[Option, Row], field: str) -> list[str]:
    both = [k for k in a.keys() & b.keys() if a[k][field] is not None and b[k][field] is not None]
    if not both:
        return []
    d = np.abs(np.array([b[k][field] - a[k][field] for k in both]))
    lines = [
        f"|Δ{field}| over {len(d):,}: mean {d.mean():.5f}, p50 {np.median(d):.5f}, "
        f"p99 {np.quantile(d, 0.99):.5f}, max {d.max():.5f}; identical {np.mean(d == 0):.1%}"
    ]
    if field == "contrast":
        se = np.array([abs(a[k]["contrast_ci"][1] - a[k]["contrast_ci"][0]) / 3.92 for k in both])
        z = d / se
        lines.append(
            f"contrast gap in a's standard errors: mean {z.mean():.3f}, "
            f"p99 {np.quantile(z, 0.99):.3f}"
        )
    return lines


def compare(a: dict[Option, Row], b: dict[Option, Row]) -> list[str]:
    common = a.keys() & b.keys()
    lines = [f"options: {len(a):,} / {len(b):,}, {len(common):,} in both"]
    lines += _gaps(a, b, "wpa") + _gaps(a, b, "contrast")
    flags: Counter[str] = Counter()
    for k in common:
        fa, fb = set(a[k]["flags"]), set(b[k]["flags"])
        flags.update([f"-{f}" for f in fa - fb] + [f"+{f}" for f in fb - fa])
    lines.append(f"flags (+ gained, - lost in b): {dict(sorted(flags.items())) or 'none'}")
    clear_a = {k for k in common if a[k]["q"] is not None and a[k]["q"] <= 0.05}
    clear_b = {k for k in common if b[k]["q"] is not None and b[k]["q"] <= 0.05}
    lines.append(
        f"q ≤ 0.05: {len(clear_a)} → {len(clear_b)} "
        f"(lost {len(clear_a - clear_b)}, gained {len(clear_b - clear_a)})"
    )
    ca, cb = choices(a), choices(b)
    slots = sorted(ca.keys() & cb.keys())
    labels_a = Counter(ca[k][1] for k in slots)
    labels_b = Counter(cb[k][1] for k in slots)
    lines.append(f"slots: {len(slots):,}; labels a {dict(labels_a)}, b {dict(labels_b)}")
    changed = [k for k in slots if ca[k][0] != cb[k][0]]
    relabelled = [k for k in slots if ca[k][0] == cb[k][0] and ca[k][1] != cb[k][1]]
    lines.append(
        f"import changes: {len(changed)} slots choose another option, {len(relabelled)} relabelled"
    )
    lines += [f"  {k}: {ca[k]} → {cb[k]}" for k in changed]
    lines += [f"  relabel {k}: {ca[k][1]} → {cb[k][1]}" for k in relabelled]
    return lines


if __name__ == "__main__":
    first, second = Path(sys.argv[1]), Path(sys.argv[2])
    print(f"{first}\n  vs {second}")
    print("\n".join(compare(load(first), load(second))))
