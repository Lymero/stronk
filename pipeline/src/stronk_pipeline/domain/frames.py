"""Per-minute game states (docs/architecture.md, section 4): the input of the `winprob` stage."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class InvalidFramesError(ValueError):
    """The table breaks an invariant; raised at construction, never later."""


@dataclass(frozen=True)
class FrameTable:
    """One row per match, minute and team, seen from that team: leads are positive when ahead.

    Both teams appear, so every situation is in the table from each side.
    """

    match_id: NDArray[np.str_]
    team: NDArray[np.int64]
    minute: NDArray[np.float64]
    outcome: NDArray[np.int64]
    features: NDArray[np.float64]
    feature_names: tuple[str, ...]

    def __post_init__(self) -> None:
        n = len(self.match_id)
        if any(c.ndim != 1 or len(c) != n for c in (self.team, self.minute, self.outcome)):
            raise InvalidFramesError("all columns must be one-dimensional with equal length")
        if self.features.shape != (n, len(self.feature_names)):
            raise InvalidFramesError(
                f"features shape {self.features.shape} != ({n}, {len(self.feature_names)})"
            )
        if not np.isin(self.team, (100, 200)).all():
            raise InvalidFramesError("team must be 100 or 200")
        if not np.isin(self.outcome, (0, 1)).all():
            raise InvalidFramesError("outcome must be 0 or 1")
        if not (np.isfinite(self.features).all() and np.isfinite(self.minute).all()):
            raise InvalidFramesError("features and minute must be finite")

    def __len__(self) -> int:
        return len(self.match_id)
