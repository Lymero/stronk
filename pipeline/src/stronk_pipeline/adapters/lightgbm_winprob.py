"""WinProbLearner on LightGBM: gradient-boosted trees on team leads and the minute.

Training is deterministic (one thread, fixed seed), so the same frames give the same model on
any machine. LightGBM's signatures mention pandas types, which aren't installed; the two ignores
below are for those.
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np

from stronk_pipeline.domain.logistic import Floats
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
        train: tuple[Floats, Floats, Floats],
        valid: tuple[Floats, Floats, Floats],
        feature_names: tuple[str, ...],
        monotone: tuple[int, ...],
        seed: int,
    ) -> WinProbModel:
        names = [*feature_names, MINUTE]
        params = {**PARAMS, "seed": seed, "monotone_constraints": [*monotone, 0]}
        train_set = lgb.Dataset(_inputs(train), label=train[2], feature_name=names)
        valid_set = lgb.Dataset(_inputs(valid), label=valid[2], reference=train_set)
        booster = lgb.train(  # pyright: ignore[reportUnknownMemberType]
            params,
            train_set,
            num_boost_round=MAX_ROUNDS,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
        )
        return LightGbmWinProb(booster, feature_names)


def _inputs(part: tuple[Floats, Floats, Floats]) -> Floats:
    features, minute, _ = part
    return np.column_stack([features, minute])
