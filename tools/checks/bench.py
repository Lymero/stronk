"""Performance scenarios for perf/budgets.toml. Writes each result to its budget's `source`.

    bench.py            every scenario that can run today

pipeline_fixtures: `just pipeline`, three times. lockin_import_cache_hit: the real core
(`stronk-core serve`, one context as in the app) against lcu-mock and the signed fixture data,
200 replays of a hover then lock-in; timed from lock-in to the import confirmed, with the plan
already loaded on hover. Needs STRONK_CORE_BIN (`just bench` builds it). Data fetch and app
start scenarios are still to come.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lcu_mock import start

ROOT = Path(__file__).resolve().parents[2]
REPEATS = 3
REPLAYS = 200
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
HOVER, LOCKED = 2, 3  # steps of SESSION: Lee Sin hovered, then locked in


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


def percentiles(samples: list[float]) -> dict[str, float]:
    """p50, p95, p99 (nearest rank) and max, rounded to 0.1."""
    ordered = sorted(samples)

    def rank(p: float) -> float:
        return ordered[max(0, math.ceil(p * len(ordered)) - 1)]

    return {
        "p50": round(rank(0.50), 1),
        "p95": round(rank(0.95), 1),
        "p99": round(rank(0.99), 1),
        "max": round(ordered[-1], 1),
    }


class Core:
    """`stronk-core serve`: one process and context, commands as JSON lines."""

    def __init__(self, binary: str, env: dict[str, str]) -> None:
        self.process = subprocess.Popen(
            [binary, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env
        )

    def run(self, command: str, params: object | None = None) -> Any:
        stdin, stdout = self.process.stdin, self.process.stdout
        if stdin is None or stdout is None:
            raise RuntimeError("stronk-core serve has no pipes")
        stdin.write(json.dumps({"id": command, "params": params or {}}) + "\n")
        stdin.flush()
        answer = json.loads(stdout.readline())
        if not answer["ok"]:
            raise RuntimeError(f"{command}: {answer['error']}")
        return answer["value"]

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.process.wait(timeout=10)


def lockin_import_cache_hit(binary: str, replays: int = REPLAYS) -> dict[str, float]:
    """Milliseconds from lock-in to the import confirmed, as the app does it: on the watcher's
    notice, `champselect.state`, then `build.import`; the plan was loaded on hover."""
    with tempfile.TemporaryDirectory() as tmp:
        mock = start(SESSION, Path(tmp) / "lcu-mock")
        env = {
            **os.environ,
            "STRONK_LCU_LOCKFILE": str(mock.lockfile),
            "STRONK_LCU_CERT": str(mock.root),
            "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
            "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
            "STRONK_BACKUP_DIR": str(Path(tmp) / "backups"),
        }
        core = Core(binary, env)
        times: list[float] = []
        try:
            for _ in range(replays):
                mock.replay.set_step(HOVER)
                hover = core.run("champselect.state")
                core.run("build.plan", {"champion": hover["champion"], "role": hover["role"]})
                mock.replay.set_step(LOCKED)
                start_ns = time.perf_counter_ns()
                state = core.run("champselect.state")
                imported = core.run("build.import")
                times.append((time.perf_counter_ns() - start_ns) / 1e6)
                if not state["session"]["locked"] or imported["runes"]["status"] != "imported":
                    raise RuntimeError(f"lock-in replay went wrong: {state} {imported}")
        finally:
            core.close()
            mock.server.shutdown()
    return percentiles(times)


def write(name: str, result: dict[str, float]) -> None:
    path = ROOT / "perf" / "out" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")


def main() -> int:
    try:
        result = measure(pipeline_fixtures)
    except subprocess.CalledProcessError as e:
        print(e.stderr, end="", file=sys.stderr)
        print(f"bench: pipeline_fixtures failed with exit code {e.returncode}", file=sys.stderr)
        return 1
    write("pipeline_fixtures", result)
    print(f"bench: pipeline_fixtures p50={result['p50']:g} s, max={result['max']:g} s")

    binary = os.environ.get("STRONK_CORE_BIN")
    if binary is None:
        print("bench: STRONK_CORE_BIN is not set (run `just bench`)", file=sys.stderr)
        return 1
    try:
        lockin = lockin_import_cache_hit(binary)
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        print(f"bench: lockin_import_cache_hit failed: {e}", file=sys.stderr)
        return 1
    write("lockin_import_cache_hit", lockin)
    shown = ", ".join(f"{k}={v:g}" for k, v in lockin.items())
    print(f"bench: lockin_import_cache_hit {shown} ms over {REPLAYS} replays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
