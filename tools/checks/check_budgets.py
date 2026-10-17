"""Check benchmark results against perf/budgets.toml. Exit 1 on a breach or a loosened budget."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from ratchet import Direction, committed, loosened, unjustified

ROOT = Path(__file__).resolve().parents[2]
LIMITS: dict[str, Direction] = {"p50": "upper", "p95": "upper", "max": "upper"}
REQUIRED = ("scenario", "description", "source", "unit", "enforce")


def check(budgets: list[dict[str, Any]], root: Path) -> tuple[list[str], list[str]]:
    """(report lines, problems)."""
    report: list[str] = []
    problems: list[str] = []
    for budget in budgets:
        name = budget.get("scenario", "?")
        missing = [k for k in REQUIRED if k not in budget]
        limits = {k: budget[k] for k in LIMITS if k in budget}
        if missing or not limits:
            problems.append(f"{name}: needs {', '.join(missing) or 'a p50, p95 or max limit'}")
            continue
        source = root / budget["source"]
        results: dict[str, float] = json.loads(source.read_text()) if source.is_file() else {}
        measured = {k: results[k] for k in (*LIMITS, "p99") if k in results}
        shown = ", ".join(f"{k}={v:g}" for k, v in measured.items()) or "not measured"
        if not budget["enforce"]:
            report.append(f"  pending  {name}: {shown} (budget {limits} {budget['unit']})")
            continue
        breaches = [k for k, limit in limits.items() if k not in results or results[k] > limit]
        status = "FAIL" if breaches else "ok"
        report.append(f"  {status:<7}  {name}: {shown} (budget {limits} {budget['unit']})")
        if breaches:
            problems.append(f"{name}: {', '.join(breaches)} over budget or not measured")
    return report, problems


def main() -> int:
    path = ROOT / "perf/budgets.toml"
    budgets = tomllib.loads(path.read_text()).get("budget", [])
    report, problems = check(budgets, ROOT)
    old = committed(path, ROOT)
    if old is not None:
        names = loosened(
            old.get("budget", []), budgets, key="scenario", limits=LIMITS, enforce_default=False
        )
        problems += [
            f"{n}: budget loosened without an entry in docs/decisions.md"
            for n in unjustified(names, ROOT / "docs/decisions.md")
        ]
    print("budgets:\n" + "\n".join(report))
    for p in problems:
        print(f"budgets: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
