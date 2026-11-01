"""Player skill from the crawl itself, using only games played before (docs/wpa-method.md, 3).

Two features per player and game, both about the champion they are playing:

- `skill_proxy`: prior win rate, shrunk toward 50% by `PRIOR_GAMES` imaginary games and
  centred on 0, so a player with no history gets 0;
- `champion_games`: log(1 + prior games), how practised they are.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from stronk_pipeline.domain.match import Match, Participant

SKILL_FEATURES = ("skill_proxy", "champion_games")
PRIOR_GAMES = 5

type PlayerGame = tuple[str, int]
"""(match_id, participant_id)."""


class Played(Protocol):
    """What skill reads of a game: a `Match`, or its `GameHeader`."""

    @property
    def match_id(self) -> str: ...
    @property
    def created_at(self) -> int: ...
    @property
    def participants(self) -> Sequence[Participant]: ...


@dataclass(frozen=True, slots=True)
class GameHeader:
    """A game without its timeline: enough for skill over many games at once, which whole
    games would not fit in memory for (ADR-079)."""

    match_id: str
    patch: str
    created_at: int
    participants: tuple[Participant, ...]

    @staticmethod
    def of(match: Match) -> GameHeader:
        return GameHeader(match.match_id, match.patch, match.created_at, match.participants)


def prior_skill(matches: Iterable[Played]) -> Mapping[PlayerGame, tuple[float, float]]:
    """SKILL_FEATURES for every player of every game, from their earlier games only."""
    record: defaultdict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    skill: dict[PlayerGame, tuple[float, float]] = {}
    for match in sorted(matches, key=lambda m: (m.created_at, m.match_id)):
        for p in match.participants:
            games, wins = record[(p.player, p.champion_id)]
            rate = (wins + PRIOR_GAMES / 2) / (games + PRIOR_GAMES)
            skill[(match.match_id, p.participant_id)] = (rate - 0.5, math.log1p(games))
        for p in match.participants:
            counts = record[(p.player, p.champion_id)]
            counts[0] += 1
            counts[1] += int(p.win)
    return skill
