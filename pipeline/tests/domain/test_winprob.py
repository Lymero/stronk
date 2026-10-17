from collections.abc import Callable

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import expit
from stronk_pipeline.domain.winprob import BaselineWinProb

type TableFactory = Callable[..., DecisionTable]


def test_predictions_are_calibrated_on_logistic_data(table_factory: TableFactory) -> None:
    rng = np.random.default_rng(1)
    n = 20_000
    gold = rng.normal(size=(n, 1))
    p = expit(0.8 * gold[:, 0])
    outcomes = (rng.random(n) < p).astype(int).tolist()
    table = table_factory(["A"] * n, outcomes, features=gold)
    predicted = BaselineWinProb.fit(table).predict(table)
    bins = np.digitize(predicted, np.linspace(0.1, 0.9, 9))
    for b in np.unique(bins):
        in_bin = bins == b
        if in_bin.sum() > 500:
            assert abs(predicted[in_bin].mean() - table.outcome[in_bin].mean()) < 0.03
