"""Every crawl of a patch at a glance: its games, whether a crawl is writing to it, and when it
last stored a game (`just crawl-status 16.22`).

    crawl      bracket      games  running  last game
    euw1-16.22 master_plus  4,699  no       9 h ago
    euw1-16.22-diamond      4,512  yes      1 min ago

A crawl that stopped long ago without reaching its target was usually stopped by an expired
development key: its log in `runs/logs/` says why, and rerunning it resumes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.domain.result import Ok


@dataclass(frozen=True)
class Crawl:
    name: str
    bracket: str
    games: int
    running: bool
    last: float | None
    """When the newest game was stored (seconds since the epoch), None without games."""


def crawls(root: Path, patch: str, writing: set[Path]) -> list[Crawl]:
    """The crawl directories of `patch` under `root`, by name."""
    found: list[Crawl] = []
    for directory in sorted(root.glob(f"*-{patch}*")):
        if not directory.is_dir():
            continue
        store = FileMatchStore(directory)
        bracket = store.bracket()
        games = list((directory / "matches").glob("*.json.gz"))
        found.append(
            Crawl(
                name=directory.name,
                bracket=bracket.value if isinstance(bracket, Ok) else "?",
                games=len(games),
                running=directory.resolve() in writing,
                last=max((g.stat().st_mtime for g in games), default=None),
            )
        )
    return found


def writing_to(commands: Iterable[str]) -> set[Path]:
    """The crawl directories running `crawl.run` commands write to."""
    out: set[Path] = set()
    for command in commands:
        if "crawl.run" not in command or "--params" not in command:
            continue
        params = command.split("--params", 1)[1].strip()
        try:
            target = json.loads(params).get("out")
        except json.JSONDecodeError:
            continue
        if isinstance(target, str):
            out.add(Path(target).resolve())
    return out


def ago(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} min ago"
    if seconds < 36 * 3600:
        return f"{round(seconds / 3600)} h ago"
    return f"{round(seconds / 86400)} days ago"


def table(found: list[Crawl], now: float) -> str:
    rows = [("crawl", "bracket", "games", "running", "last game")]
    rows += [
        (
            c.name,
            c.bracket,
            f"{c.games:,}",
            "yes" if c.running else "no",
            "-" if c.last is None else ago(now - c.last),
        )
        for c in found
    ]
    rows.append(("total", "", f"{sum(c.games for c in found):,}", "", ""))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    right = {2}
    return "\n".join(
        "  ".join(
            v.rjust(w) if i in right else v.ljust(w)
            for i, (v, w) in enumerate(zip(r, widths, strict=True))
        ).rstrip()
        for r in rows
    )


def _commands() -> list[str]:
    done = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, check=False)  # noqa: S607
    return done.stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("patch", help="for example 16.22")
    parser.add_argument("--root", type=Path, default=Path("runs/crawl"))
    args = parser.parse_args()
    found = crawls(args.root, args.patch, writing_to(_commands()))
    if not found:
        print(f"no crawl of {args.patch} in {args.root}")
        return 1
    print(table(found, time.time()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
