from collections.abc import Callable

import numpy as np
import pytest
from winprob_builders import GOLD, frames, truth

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats, expit
from stronk_pipeline.domain.winprob import (
    WP_FEATURES,
    WP_MONOTONE,
    BaselineWinProb,
    LogisticLearner,
    MissingFeaturesError,
    columns,
    split_by_match,
    symmetric,
)

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


def test_split_keeps_each_match_whole_and_ignores_order() -> None:
    table = frames(40)
    split = split_by_match(table.match_id)
    parts = (split.train, split.valid, split.test)
    assert (np.sum(parts, axis=0) == 1).all()
    seen = [set(table.match_id[p].tolist()) for p in parts]
    assert not seen[0] & seen[1]
    assert not seen[0] & seen[2]
    assert not seen[1] & seen[2]
    assert [len(s) for s in seen] == [28, 6, 6]
    reversed_ids = table.match_id[::-1]
    again = split_by_match(reversed_ids)
    assert set(reversed_ids[again.test].tolist()) == seen[2]


def test_split_of_three_matches_gives_one_each() -> None:
    ids = np.array(["a", "a", "b", "c"])
    split = split_by_match(ids)
    assert [len(set(ids[p].tolist())) for p in (split.train, split.valid, split.test)] == [1, 1, 1]


def test_split_needs_three_matches() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        split_by_match(np.array(["a", "b"]))


def test_columns_by_name() -> None:
    x = np.array([[1.0, 2.0, 3.0]])
    assert columns(x, ("a", "b", "c"), ("c", "a")).tolist() == [[3.0, 1.0]]
    with pytest.raises(MissingFeaturesError, match="d"):
        columns(x, ("a", "b", "c"), ("d",))


def test_symmetric_probabilities_add_up_to_one() -> None:
    def lopsided(x: Floats, minute: Floats) -> Floats:
        return expit(x[:, 0] + 0.3)  # favours whoever is asked

    x, minute = np.array([[1.0], [-2.0]]), np.zeros(2)
    total = symmetric(lopsided, x, minute) + symmetric(lopsided, -x, minute)
    assert total == pytest.approx(np.ones(2))


def test_logistic_learner_recovers_a_logistic_truth() -> None:
    table = frames(400, seed=3)
    x = columns(table.features, table.feature_names, WP_FEATURES)
    y = table.outcome.astype(np.float64)
    part = (x, table.minute, y)
    model = LogisticLearner().fit(part, part, WP_FEATURES, WP_MONOTONE, 0)
    late = table.minute == 24
    predicted = symmetric(model.predict, x[late], table.minute[late])
    expected = truth(x[late, GOLD], table.minute[late])
    assert np.mean(np.abs(predicted - expected)) < 0.05
