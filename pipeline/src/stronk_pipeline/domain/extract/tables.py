"""Matches -> frame and decision tables, with counts of everything dropped on the way."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.extract.decision_points import decision_points
from stronk_pipeline.domain.extract.situation import (
    PLAYER_FEATURES,
    SITUATION_FEATURES,
    player_situation,
    situation,
)
from stronk_pipeline.domain.extract.skill import SKILL_FEATURES, prior_skill
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.match import TEAMS, Match
from stronk_pipeline.domain.static import StaticData

DECISION_FEATURES = (*SITUATION_FEATURES, *PLAYER_FEATURES, *SKILL_FEATURES)


@dataclass
class ExtractStats:
    matches: int = 0
    decisions_by_slot: Counter[int] = field(default_factory=Counter[int])
    inferred: int = 0
    """Decisions on an unfinished slot whose option came from its components."""
    dropped: Counter[str] = field(default_factory=Counter[str])
    """Matches or decisions left out, by reason."""


@dataclass(frozen=True)
class Extracted:
    frames: FrameTable
    decisions: DecisionTable
    stats: ExtractStats


def extract(matches: Sequence[Match], statics: Mapping[str, StaticData]) -> Extracted:
    """Build both tables. `statics` maps a patch to its game data; matches without it drop."""
    stats = ExtractStats()
    usable = [m for m in matches if _usable(m, statics, stats)]
    skill = prior_skill(matches)
    frames = _Columns()
    decisions = _Columns()
    for match in usable:
        stats.matches += 1
        static = statics[match.patch]
        for frame in match.frames[1:]:
            for team in TEAMS:
                frames.add(
                    match_id=match.match_id,
                    team=team,
                    minute=frame.timestamp / 60_000,
                    outcome=int(team == match.winning_team),
                    features=situation(match, frame.timestamp, team),
                )
        for point in decision_points(match, static, stats.dropped):
            p = match.participant(point.participant_id)
            champion = static.champions[p.champion_id]
            stats.decisions_by_slot[point.slot] += 1
            stats.inferred += int(point.inferred)
            decisions.add(
                match_id=match.match_id,
                participant=p.participant_id,
                champion=champion.name,
                champion_class=champion.champion_class,
                role=p.position,
                slot=point.slot,
                minute=point.timestamp / 60_000,
                option=point.option,
                outcome=int(p.win),
                features=(
                    *situation(match, point.timestamp, p.team),
                    *player_situation(match, point.timestamp, p, static),
                    *skill[(match.match_id, p.participant_id)],
                ),
            )
    return Extracted(
        frames=FrameTable(
            match_id=frames.strings("match_id"),
            team=frames.ints("team"),
            minute=frames.floats("minute"),
            outcome=frames.ints("outcome"),
            features=frames.matrix(len(SITUATION_FEATURES)),
            feature_names=SITUATION_FEATURES,
        ),
        decisions=DecisionTable.create(
            match_id=decisions.strings("match_id"),
            participant=decisions.ints("participant"),
            champion=decisions.strings("champion"),
            champion_class=decisions.strings("champion_class"),
            role=decisions.strings("role"),
            slot=decisions.ints("slot"),
            minute=decisions.floats("minute"),
            option=decisions.strings("option"),
            outcome=decisions.ints("outcome"),
            features=decisions.matrix(len(DECISION_FEATURES)),
            feature_names=DECISION_FEATURES,
        ),
        stats=stats,
    )


def _usable(match: Match, statics: Mapping[str, StaticData], stats: ExtractStats) -> bool:
    static = statics.get(match.patch)
    if static is None:
        stats.dropped["no_static_data"] += 1
        return False
    if any(p.champion_id not in static.champions for p in match.participants):
        stats.dropped["unknown_champion"] += 1
        return False
    return True


class _Columns:
    """Row-wise accumulation, column-wise output."""

    def __init__(self) -> None:
        self._values: dict[str, list[object]] = {}
        self._features: list[tuple[float, ...]] = []

    def add(self, *, features: tuple[float, ...], **values: object) -> None:
        for name, value in values.items():
            self._values.setdefault(name, []).append(value)
        self._features.append(features)

    def strings(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.str_]]:
        return np.array(self._values.get(name, []), dtype=np.str_)

    def ints(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.int64]]:
        return np.array(self._values.get(name, []), dtype=np.int64)

    def floats(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        return np.array(self._values.get(name, []), dtype=np.float64)

    def matrix(self, width: int) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
        return np.array(self._features, dtype=np.float64).reshape(len(self._features), width)
