"""Check quality metrics against metrics/floors.toml. Exit 1 on a breach or a loosened floor."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from ratchet import Direction, committed, loosened, unjustified

ROOT = Path(__file__).resolve().parents[2]
LIMITS: dict[str, Direction] = {"max": "upper", "min": "lower"}


def check(floors: list[dict[str, Any]], root: Path) -> tuple[list[str], list[str]]:
    """(report lines, problems)."""
    report: list[str] = []
    problems: list[str] = []
    cache: dict[Path, dict[str, Any] | None] = {}
    for floor in floors:
        metric = floor["metric"]
        source = root / floor["source"]
        if source not in cache:
            cache[source] = json.loads(source.read_text()) if source.is_file() else None
        values = cache[source]
        value = None if values is None else values.get(metric)
        bounds = {k: floor[k] for k in ("min", "max") if k in floor}
        enforced = floor.get("enforce", True) and bounds
        if not enforced:
            report.append(f"  pending  {metric} = {value if value is not None else '-'}")
            continue
        if value is None:
            problems.append(f"{metric}: no value in {floor['source']}")
            continue
        breached = ("min" in bounds and value < bounds["min"]) or (
            "max" in bounds and value > bounds["max"]
        )
        status = "FAIL" if breached else "ok"
        report.append(f"  {status:<7}  {metric} = {value:.6g}  {bounds}")
        if breached:
            problems.append(f"{metric} = {value:.6g} breaks floor {bounds}")
    return report, problems


def main() -> int:
    path = ROOT / "metrics/floors.toml"
    floors = tomllib.loads(path.read_text()).get("floor", [])
    report, problems = check(floors, ROOT)
    old = committed(path, ROOT)
    if old is not None:
        names = loosened(
            old.get("floor", []), floors, key="metric", limits=LIMITS, enforce_default=True
        )
        problems += [
            f"{n}: floor loosened without an entry in docs/decisions.md"
            for n in unjustified(names, ROOT / "docs/decisions.md")
        ]
    print("floors:\n" + "\n".join(report))
    for p in problems:
        print(f"floors: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
