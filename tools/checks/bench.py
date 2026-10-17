"""Performance scenarios for perf/budgets.toml. Writes each result to its budget's `source`.

    bench.py            every scenario that can run today (pipeline_fixtures)

Lock-in, data fetch and app start scenarios arrive with the app (M3).
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPEATS = 3


def measure(
    run: Callable[[], None], repeats: int = REPEATS, clock: Callable[[], float] = time.perf_counter
) -> dict[str, float]:
    """Wall time of `repeats` runs, in seconds: p50 and max (budgets enforce max)."""
    times: list[float] = []
    for _ in range(repeats):
        start = clock()
        run()
        times.append(clock() - start)
    return {"p50": round(statistics.median(times), 3), "max": round(max(times), 3)}


def pipeline_fixtures() -> None:
    """The whole pipeline on the committed recording, as `just pipeline` runs it."""
    out = ROOT / "runs" / "bench" / "pipeline"
    subprocess.run(
        ["just", "pipeline", str(out)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    try:
        result = measure(pipeline_fixtures)
    except subprocess.CalledProcessError as e:
        print(e.stderr, end="", file=sys.stderr)
        print(f"bench: pipeline_fixtures failed with exit code {e.returncode}", file=sys.stderr)
        return 1
    path = ROOT / "perf" / "out" / "pipeline_fixtures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"bench: pipeline_fixtures p50={result['p50']:g} s, max={result['max']:g} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
