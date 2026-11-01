"""WinProbLearner on LightGBM: gradient-boosted trees on team leads and the minute.

Training is deterministic (one thread, fixed seed), so the same frames give the same model on
any machine. LightGBM's signatures mention pandas types, which aren't installed; the ignores
below are for those.

Rows reach LightGBM a chunk at a time, through its `Sequence` interface (ADR-081): it samples
rows for its bin edges, then reads the rest in ranges, and keeps them binned, a byte per feature.
The model is the one from all rows in one array: the sample is drawn with the same seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np

from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.winprob import Rows
from stronk_pipeline.ports import WinProbModel

MINUTE = "minute"
MAX_ROUNDS = 2000
EARLY_STOPPING = 50
PARAMS: dict[str, object] = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_data_in_leaf": 200,
    "lambda_l2": 1.0,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbosity": -1,
}


@dataclass(frozen=True)
class LightGbmWinProb:
    booster: lgb.Booster
    feature_names: tuple[str, ...]

    def predict(self, features: Floats, minute: Floats) -> Floats:
        inputs = np.column_stack([features, minute])
        raw = self.booster.predict(inputs)  # pyright: ignore[reportUnknownMemberType]
        return np.asarray(raw, dtype=np.float64).reshape(len(features))


class LightGbmLearner:
    id = "lightgbm"

    def fit(
        self,
        train: Rows,
        valid: Rows,
        feature_names: tuple[str, ...],
        monotone: tuple[int, ...],
        seed: int,
    ) -> WinProbModel:
        names = [*feature_names, MINUTE]
        params = {
            **PARAMS,
            "seed": seed,
            "data_random_seed": data_seed(seed),
            "monotone_constraints": [*monotone, 0],
        }
        cache = _Cache()
        train_set = lgb.Dataset(
            _sequences(train, cache),
            label=_labels(train),
            feature_name=names,
            params=params,
        )
        valid_set = lgb.Dataset(
            _sequences(valid, cache), label=_labels(valid), reference=train_set, params=params
        )
        booster = lgb.train(  # pyright: ignore[reportUnknownMemberType]
            params,
            train_set,
            num_boost_round=MAX_ROUNDS,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
        )
        return LightGbmWinProb(booster, feature_names)


def data_seed(seed: int) -> int:
    """The seed LightGBM derives from `seed` for sampling the rows its bin edges come from: the
    first draw of its generator (`Random::NextShort`, a linear congruential step). Rows given as
    an array get it from `seed`; rows given as a `Sequence` only from `data_random_seed`, so it
    is passed explicitly, and the two give the same model."""
    state = (214013 * seed + 2531011) % 2**32
    return ((state >> 16) & 0x7FFF) % 32767


@dataclass
class _Cache:
    """The one chunk in memory: LightGBM reads chunks in order, each whole before the next."""

    key: tuple[int, int] | None = None
    rows: Floats = field(default_factory=lambda: np.empty((0, 0)))

    def get(self, rows: Rows, index: int) -> Floats:
        if self.key != (id(rows), index):
            features, minute, _ = rows.load(index)
            self.key, self.rows = (id(rows), index), np.column_stack([features, minute])
        return self.rows


class _Chunk(lgb.Sequence):
    def __init__(self, rows: Rows, index: int, cache: _Cache) -> None:
        self.rows, self.index, self.cache = rows, index, cache
        self.batch_size = 4096

    def __len__(self) -> int:
        return self.rows.sizes[self.index]

    def __getitem__(self, idx: int | slice | list[int]) -> Floats:
        return self.cache.get(self.rows, self.index)[idx]


def _sequences(rows: Rows, cache: _Cache) -> list[lgb.Sequence]:
    return [_Chunk(rows, i, cache) for i, n in enumerate(rows.sizes) if n > 0]


def _labels(rows: Rows) -> Floats:
    return np.concatenate([y for _, _, y in rows.chunks()]) if rows.sizes else np.empty(0)
