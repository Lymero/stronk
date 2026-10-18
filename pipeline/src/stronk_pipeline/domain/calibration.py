"""How well predicted win probabilities match observed win rates (docs/wpa-method.md, section 4).

Calibration matters more than accuracy for WPA: a predicted 60% should win about 60% of the
time, at every stage of the game.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stronk_pipeline.domain.logistic import Floats

BINS = 10
"""Equal-width probability bins for the reliability table and calibration error."""
MINUTE_BANDS = ((0.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, float("inf")))
EPS = 1e-12


@dataclass(frozen=True)
class Bin:
    low: float
    high: float
    n: int
    predicted: float
    observed: float


@dataclass(frozen=True)
class Band:
    low: float
    high: float
    n: int
    log_loss: float
    calibration_error: float


@dataclass(frozen=True)
class CalibrationReport:
    n: int
    log_loss: float
    brier: float
    calibration_error: float
    """Expected calibration error: the n-weighted mean gap between predicted and observed win
    rate over the bins."""
    bins: tuple[Bin, ...]
    by_minute: tuple[Band, ...]


def log_loss(y: Floats, p: Floats) -> float:
    q = np.clip(p, EPS, 1.0 - EPS)
    return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))) if len(y) else 0.0


def calibration_error(y: Floats, p: Floats) -> float:
    return sum(b.n * abs(b.predicted - b.observed) for b in _bins(y, p)) / max(len(y), 1)


def calibration(y: Floats, p: Floats, minute: Floats) -> CalibrationReport:
    """`y` outcomes (0 or 1), `p` predicted probabilities, `minute` of each prediction."""
    bands: list[Band] = []
    for low, high in MINUTE_BANDS:
        mask = (minute >= low) & (minute < high)
        if mask.any():
            yb, pb = y[mask], p[mask]
            bands.append(
                Band(low, high, int(mask.sum()), log_loss(yb, pb), calibration_error(yb, pb))
            )
    return CalibrationReport(
        n=len(y),
        log_loss=log_loss(y, p),
        brier=float(np.mean((p - y) ** 2)) if len(y) else 0.0,
        calibration_error=calibration_error(y, p),
        bins=tuple(_bins(y, p)),
        by_minute=tuple(bands),
    )


def _bins(y: Floats, p: Floats) -> list[Bin]:
    index = np.minimum((p * BINS).astype(np.int64), BINS - 1)
    bins: list[Bin] = []
    for i in range(BINS):
        mask = index == i
        if mask.any():
            low, high = i / BINS, (i + 1) / BINS
            predicted, observed = float(p[mask].mean()), float(y[mask].mean())
            bins.append(Bin(low, high, int(mask.sum()), predicted, observed))
    return bins
