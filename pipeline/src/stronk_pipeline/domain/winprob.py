"""Win probability: the model inputs, the train/validation/test split, and the logistic model.

`winprob.train` fits every learner (this logistic one, LightGBM in adapters/) on per-minute
frames and keeps the best on validation. `BaselineWinProb` is the same logistic form fitted on
the decisions themselves: `wpa.estimate` falls back to it when no trained model is given, as on
synthetic games, which have no frames.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.extract.situation import SITUATION_FEATURES
from stronk_pipeline.domain.logistic import (
    Floats,
    LogisticModel,
    fit_logistic,
    fit_logistic_chunks,
)

WP_FEATURES = SITUATION_FEATURES
"""What the model reads besides the minute: team leads, each from the predicted team's side."""
WP_MONOTONE = tuple(1 for _ in WP_FEATURES)
"""A bigger lead never lowers the chance to win: every feature is constrained to help."""
SHARES = (0.70, 0.15)
"""Train and validation shares of matches; the rest is the test set."""

type Predict = Callable[[Floats, Floats], Floats]
"""(features in WP_FEATURES order, minute) -> P(win)."""


class MissingFeaturesError(ValueError):
    pass


@dataclass(frozen=True)
class Split:
    train: NDArray[np.bool_]
    valid: NDArray[np.bool_]
    test: NDArray[np.bool_]


TRAIN, VALID, TEST = 0, 1, 2
"""The parts of the split, as `match_parts` numbers them."""


def match_parts(match_ids: Iterable[str]) -> dict[str, int]:
    """The part of each match: matches ordered by a hash of their id, the first `SHARES[0]` to
    training, the next `SHARES[1]` to validation, the rest to test. Stable and independent of
    order; needs at least 3 matches, and each part gets at least one."""
    matches = sorted(set(match_ids), key=_hash)
    n = len(matches)
    if n < 3:
        raise ValueError(f"need at least 3 matches to split, got {n}")
    n_train = min(max(1, round(SHARES[0] * n)), n - 2)
    n_valid = min(max(1, round(SHARES[1] * n)), n - n_train - 1)
    return {
        m: TRAIN if i < n_train else VALID if i < n_train + n_valid else TEST
        for i, m in enumerate(matches)
    }


def split_by_match(match_id: NDArray[np.str_]) -> Split:
    """Every row of a match in the same part (`match_parts`), so no game is seen in training
    and tested on."""
    parts = match_parts(match_id.tolist())
    position = np.array([parts[m] for m in match_id.tolist()], dtype=np.int64)
    return Split(train=position == TRAIN, valid=position == VALID, test=position == TEST)


@dataclass(frozen=True)
class Rows:
    """Training rows, (features in WP_FEATURES order, minute, outcome), read a chunk at a time,
    so frames larger than memory are never held whole (ADR-081): chunk `i` has `sizes[i]` rows
    and `load(i)` reads it. Rows in memory are one chunk (`Rows.of`)."""

    sizes: tuple[int, ...]
    load: Callable[[int], tuple[Floats, Floats, Floats]]

    @staticmethod
    def of(features: Floats, minute: Floats, outcome: Floats) -> Rows:
        return Rows((len(outcome),), lambda _: (features, minute, outcome))

    def __len__(self) -> int:
        return sum(self.sizes)

    def chunks(self) -> Iterator[tuple[Floats, Floats, Floats]]:
        return (self.load(i) for i in range(len(self.sizes)))


def columns(features: Floats, names: Sequence[str], wanted: Sequence[str]) -> Floats:
    """The `wanted` columns of `features`, by name: stored tables don't keep column order."""
    index = {name: i for i, name in enumerate(names)}
    missing = [w for w in wanted if w not in index]
    if missing:
        raise MissingFeaturesError(f"missing features: {', '.join(missing)}")
    return features[:, [index[w] for w in wanted]]


def symmetric(predict: Predict, x: Floats, minute: Floats) -> Floats:
    """Leads are differences, so the other team sees -x. Averaging p(x) with 1 - p(-x) makes
    both teams' probabilities of the same moment add up to exactly 1."""
    return 0.5 * (predict(x, minute) + 1.0 - predict(-x, minute))


@dataclass(frozen=True)
class LogisticWinProb:
    """A `WinProbModel`: logistic regression on leads, minute and their interaction."""

    feature_names: tuple[str, ...]
    model: LogisticModel

    def predict(self, features: Floats, minute: Floats) -> Floats:
        return self.model.predict(_inputs(features, minute))


class LogisticLearner:
    """A `WinProbLearner`. Ignores `monotone`: with one coefficient per lead and per lead x
    minute, monotonicity holds wherever the fitted signs agree, and isn't forced."""

    id = "logistic"

    def fit(
        self,
        train: Rows,
        valid: Rows,
        feature_names: tuple[str, ...],
        monotone: tuple[int, ...],
        seed: int,
    ) -> LogisticWinProb:
        def chunks() -> Iterator[tuple[Floats, Floats]]:
            return ((_inputs(x, minute), y) for x, minute, y in train.chunks())

        return LogisticWinProb(feature_names, fit_logistic_chunks(chunks))


@dataclass(frozen=True)
class BaselineWinProb:
    """The baseline fitted on decisions, on every situation feature they carry."""

    model: LogisticModel

    @classmethod
    def fit(cls, table: DecisionTable) -> BaselineWinProb:
        y = table.outcome.astype(np.float64)
        return cls(fit_logistic(_inputs(table.features, table.minute), y))

    def predict(self, table: DecisionTable) -> Floats:
        return self.model.predict(_inputs(table.features, table.minute))


def _inputs(x: Floats, minute: Floats) -> Floats:
    """Features, minute, and their interaction: the same lead matters more later on."""
    m = minute[:, None]
    return np.hstack([x, m, x * m])


def _hash(match_id: str) -> str:
    return hashlib.sha256(match_id.encode()).hexdigest()
