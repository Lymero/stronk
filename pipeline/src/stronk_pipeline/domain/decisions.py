"""Decision points (docs/wpa-method.md, section 2) as a validated columnar table."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

type DecisionKey = tuple[str, str, int]
"""(champion, role, slot): the decision point an option is chosen at."""


class InvalidDecisionsError(ValueError):
    """The table breaks an invariant; raised at construction, never later."""


@dataclass(frozen=True)
class DecisionTable:
    """One row per decision: a player choosing an option at a decision point.

    `features` are the situation at decision time (game state, skill proxy...), the inputs of
    the win probability and propensity models. Rows are in canonical order and unique per
    (match, participant, champion, role, slot, minute), so results never depend on input order
    and duplicated matches count once; a player's several late items (ADR-067) share a slot
    but not a minute.
    """

    match_id: NDArray[np.str_]
    participant: NDArray[np.int64]
    champion: NDArray[np.str_]
    champion_class: NDArray[np.str_]
    role: NDArray[np.str_]
    slot: NDArray[np.int64]
    minute: NDArray[np.float64]
    option: NDArray[np.str_]
    outcome: NDArray[np.int64]
    features: NDArray[np.float64]
    feature_names: tuple[str, ...]

    def __post_init__(self) -> None:
        n = len(self.match_id)
        columns = (
            self.participant,
            self.champion,
            self.champion_class,
            self.role,
            self.slot,
            self.minute,
            self.option,
            self.outcome,
        )
        if any(c.ndim != 1 or len(c) != n for c in (self.match_id, *columns)):
            raise InvalidDecisionsError("all columns must be one-dimensional with equal length")
        if self.features.shape != (n, len(self.feature_names)):
            raise InvalidDecisionsError(
                f"features shape {self.features.shape} != ({n}, {len(self.feature_names)})"
            )
        if len(set(self.feature_names)) != len(self.feature_names):
            raise InvalidDecisionsError("feature names must be unique")
        if not np.isin(self.outcome, (0, 1)).all():
            raise InvalidDecisionsError("outcome must be 0 or 1")
        if not (np.isfinite(self.features).all() and np.isfinite(self.minute).all()):
            raise InvalidDecisionsError("features and minute must be finite")
        if (self.slot < 0).any():
            raise InvalidDecisionsError("slot must be non-negative (0 is champion select)")

    @classmethod
    def create(
        cls,
        *,
        match_id: NDArray[np.str_],
        participant: NDArray[np.int64],
        champion: NDArray[np.str_],
        champion_class: NDArray[np.str_],
        role: NDArray[np.str_],
        slot: NDArray[np.int64],
        minute: NDArray[np.float64],
        option: NDArray[np.str_],
        outcome: NDArray[np.int64],
        features: NDArray[np.float64],
        feature_names: tuple[str, ...],
    ) -> DecisionTable:
        """Validate, sort canonically and drop duplicate decisions."""
        raw = cls(
            match_id,
            participant,
            champion,
            champion_class,
            role,
            slot,
            minute,
            option,
            outcome,
            features,
            feature_names,
        )
        order = np.lexsort(
            (raw.minute, raw.participant, raw.match_id, raw.slot, raw.role, raw.champion)
        )
        sorted_ = raw.take(order)
        identity = np.rec.fromarrays(
            [
                sorted_.champion,
                sorted_.role,
                sorted_.slot,
                sorted_.match_id,
                sorted_.participant,
                sorted_.minute,
            ]
        )
        keep = np.ones(len(sorted_), dtype=bool)
        keep[1:] = identity[1:] != identity[:-1]
        return sorted_.take(np.flatnonzero(keep))

    def __len__(self) -> int:
        return len(self.match_id)

    def take(self, indices: NDArray[np.intp]) -> DecisionTable:
        return DecisionTable(
            self.match_id[indices],
            self.participant[indices],
            self.champion[indices],
            self.champion_class[indices],
            self.role[indices],
            self.slot[indices],
            self.minute[indices],
            self.option[indices],
            self.outcome[indices],
            self.features[indices],
            self.feature_names,
        )

    def decision_points(self) -> Iterator[tuple[DecisionKey, NDArray[np.intp]]]:
        """Each decision point with the row indices of its decisions, in canonical order."""
        keys = sorted(
            {
                (str(c), str(r), int(s))
                for c, r, s in zip(self.champion, self.role, self.slot, strict=True)
            }
        )
        for champion, role, slot in keys:
            mask = (self.champion == champion) & (self.role == role) & (self.slot == slot)
            yield (champion, role, slot), np.flatnonzero(mask)
