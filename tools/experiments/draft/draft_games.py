"""Every crawled game's draft as one table: who played which champion in which role, and won.

    uv run python tools/experiments/draft/draft_games.py <out.parquet> <crawl> [<crawl> …]

Reads only the start of each stored game (its participants come before the timeline), so a
crawl of 20,000 games takes seconds. One row per player and game, with two features from that
player's earlier games in the same crawl (players are hashed per crawl, docs/wpa-method.md 3):

- `skill`: their prior win rate on *other* champions, shrunk toward 50% by `PRIOR_GAMES` and
  centred on 0. Other champions only, so a champion's own strength doesn't leak into the
  skill of the players who spam it.
- `practice`: log(1 + their prior games on this champion), how practised they are.

A game stored in several crawls (a Master+ game also found from the Diamond ladder) is kept
once, from the first crawl named.
"""

from __future__ import annotations

import gzip
import json
import math
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import polars as pl

PRIOR_GAMES = 10
HEAD_BYTES = 12_000
type Row = tuple[str, str, str, str, str, int, int, str, int, bool, float, float]
"""One player of one game, in COLUMNS' order."""

COLUMNS = (
    "match_id",
    "crawl",
    "platform",
    "patch",
    "bracket",
    "created_at",
    "team",
    "position",
    "champion",
    "win",
    "skill",
    "practice",
)


@dataclass(frozen=True, slots=True)
class Seat:
    player: str
    team: int
    position: str
    champion: int
    win: bool


@dataclass(frozen=True, slots=True)
class Game:
    match_id: str
    platform: str
    patch: str
    created_at: int
    seats: tuple[Seat, ...]


def read_head(path: Path) -> Game | None:
    """The game's header and participants, from the first bytes of its file when they hold
    them, else the whole file; None for a file that isn't a whole ten-player game."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            text = f.read(HEAD_BYTES)
            data = _head(text)
            if data is None:
                data = cast("dict[str, Any]", json.loads(text + f.read()))
    except (OSError, EOFError, ValueError):
        return None
    participants = cast("list[dict[str, Any]]", data["participants"])
    seats = tuple(
        Seat(
            str(p["player"]),
            int(p["team"]),
            str(p["position"]),
            int(p["champion_id"]),
            bool(p["win"]),
        )
        for p in participants
    )
    if len(seats) != 10 or sorted(s.position for s in seats) != sorted(2 * POSITIONS):
        return None
    return Game(
        str(data["match_id"]),
        str(data["platform"]),
        str(data["patch"]),
        int(data["created_at"]),
        seats,
    )


POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _head(text: str) -> dict[str, Any] | None:
    start = text.find('"participants":[')
    if start < 0:
        return None
    try:
        participants, _ = json.JSONDecoder().raw_decode(text, start + len('"participants":'))
        header = cast("dict[str, Any]", json.loads(text[:start] + '"participants":[]}'))
    except ValueError:
        return None
    header["participants"] = participants
    return header


def features(games: Iterable[Game]) -> dict[tuple[str, str], tuple[float, float]]:
    """(skill, practice) per (match_id, player), each from the player's earlier games only."""
    total: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    on: defaultdict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    out: dict[tuple[str, str], tuple[float, float]] = {}
    for game in sorted(games, key=lambda g: (g.created_at, g.match_id)):
        for s in game.seats:
            games_all, wins_all = total[s.player]
            games_on, wins_on = on[(s.player, s.champion)]
            games_other, wins_other = games_all - games_on, wins_all - wins_on
            rate = (wins_other + PRIOR_GAMES / 2) / (games_other + PRIOR_GAMES)
            out[(game.match_id, s.player)] = (rate - 0.5, math.log1p(games_on))
        for s in game.seats:
            for counts in (total[s.player], on[(s.player, s.champion)]):
                counts[0] += 1
                counts[1] += int(s.win)
    return out


def rows(crawl: Path, workers: int = 16) -> list[Row]:
    bracket_file = crawl / "bracket.txt"
    bracket = bracket_file.read_text().strip() if bracket_file.exists() else "master_plus"
    paths = sorted((crawl / "matches").glob("*.json.gz"))
    with ProcessPoolExecutor(workers) as pool:
        games = [g for g in pool.map(read_head, paths, chunksize=256) if g is not None]
    skill = features(games)
    return [
        (
            g.match_id,
            crawl.name,
            g.platform,
            g.patch,
            bracket,
            g.created_at,
            s.team,
            s.position,
            s.champion,
            s.win,
            *skill[(g.match_id, s.player)],
        )
        for g in games
        for s in g.seats
    ]


def table(crawls: Sequence[Path]) -> pl.DataFrame:
    seen: set[str] = set()
    out: list[Row] = []
    for crawl in crawls:
        mine = [r for r in rows(crawl) if r[0] not in seen]
        seen.update(r[0] for r in mine)
        out.extend(mine)
        print(f"{crawl.name}: {len(mine) // 10} games", file=sys.stderr)
    return pl.DataFrame(out, schema=list(COLUMNS), orient="row")


def main(argv: Sequence[str]) -> None:
    out, *crawls = argv
    frame = table([Path(c) for c in crawls])
    frame.write_parquet(out)
    print(f"{frame.height // 10} games into {out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
