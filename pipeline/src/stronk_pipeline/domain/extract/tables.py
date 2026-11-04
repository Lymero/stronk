"""Matches -> frame and decision tables, with counts of everything dropped on the way."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.extract.decision_points import (
    LATE_SLOT,
    PURCHASE_SLOTS,
    DecisionPoint,
    decision_points,
)
from stronk_pipeline.domain.extract.situation import (
    PLAYER_FEATURES,
    SITUATION_FEATURES,
    player_situation,
    situation,
)
from stronk_pipeline.domain.extract.skill import SKILL_FEATURES, PlayerGame, prior_skill
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

    def add(self, other: ExtractStats) -> None:
        """Count `other`'s games too: one chunk of games after another (ADR-080)."""
        self.matches += other.matches
        self.decisions_by_slot.update(other.decisions_by_slot)
        self.inferred += other.inferred
        self.dropped.update(other.dropped)


@dataclass(frozen=True)
class Extracted:
    frames: FrameTable
    decisions: DecisionTable
    stats: ExtractStats


def extract(
    matches: Iterable[Match],
    statics: Mapping[str, StaticData],
    skill: Mapping[PlayerGame, tuple[float, float]] | None = None,
    changed: Mapping[str, frozenset[int]] | None = None,
) -> Extracted:
    """Build both tables. `statics` maps a patch to its game data; matches without it drop.
    `skill` is `prior_skill` over every game; given, `matches` are read once, one at a time,
    so they can stream from disk (ADR-079). `changed` maps an older patch to the items changed
    since (`patches.changed_since`): its games' choices of those items are left out, so they are
    measured on the newest patch alone (ADR-088)."""
    if skill is None:
        matches = list(matches)
        skill = prior_skill(matches)
    stats = ExtractStats()
    frames = _Columns()
    decisions = _Columns()
    for match in matches:
        if not _usable(match, statics, stats):
            continue
        stats.matches += 1
        static = statics[match.patch]
        gone = (changed or {}).get(match.patch, frozenset[int]())
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
            if gone and _buys_any(point, gone):
                stats.dropped["changed_item_older_patch"] += 1
                continue
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


def _buys_any(point: DecisionPoint, items: frozenset[int]) -> bool:
    """An item decision (a slot, the start, the first components, boots) whose option holds one
    of `items`."""
    if not (1 <= point.slot <= LATE_SLOT or point.slot in PURCHASE_SLOTS):
        return False
    return any(int(i) in items for i in point.option.split(","))


def _usable(match: Match, statics: Mapping[str, StaticData], stats: ExtractStats) -> bool:
    static = statics.get(match.patch)
    if static is None:
        stats.dropped["no_static_data"] += 1
        return False
    if any(p.champion_id not in static.champions for p in match.participants):
        stats.dropped["unknown_champion"] += 1
        return False
    return True


_BLOCK = 65_536
"""Feature rows kept as Python floats before they become one float64 block: a quarter of the
memory, for tables of millions of rows (ADR-079)."""


class _Columns:
    """Row-wise accumulation, column-wise output."""

    def __init__(self) -> None:
        self._values: dict[str, list[object]] = {}
        self._features: list[tuple[float, ...]] = []
        self._blocks: list[np.ndarray[tuple[int, int], np.dtype[np.float64]]] = []

    def add(self, *, features: tuple[float, ...], **values: object) -> None:
        for name, value in values.items():
            self._values.setdefault(name, []).append(value)
        self._features.append(features)
        if len(self._features) == _BLOCK:
            self._blocks.append(np.array(self._features, dtype=np.float64))
            self._features = []

    def strings(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.str_]]:
        return np.array(self._values.get(name, []), dtype=np.str_)

    def ints(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.int64]]:
        return np.array(self._values.get(name, []), dtype=np.int64)

    def floats(self, name: str) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        return np.array(self._values.get(name, []), dtype=np.float64)

    def matrix(self, width: int) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
        rest = np.array(self._features, dtype=np.float64).reshape(len(self._features), width)
        return np.concatenate([*self._blocks, rest]) if self._blocks else rest
