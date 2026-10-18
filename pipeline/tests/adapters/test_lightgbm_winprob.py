import numpy as np
from winprob_builders import GOLD, frames

from stronk_pipeline.adapters.lightgbm_winprob import LightGbmLearner
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.winprob import WP_FEATURES, WP_MONOTONE, columns, split_by_match

type Part = tuple[Floats, Floats, Floats]


def parts(matches: int = 300) -> tuple[Part, Part]:
    table = frames(matches, seed=5)
    x = columns(table.features, table.feature_names, WP_FEATURES)
    y = table.outcome.astype(np.float64)
    split = split_by_match(table.match_id)
    return (
        (x[split.train], table.minute[split.train], y[split.train]),
        (x[split.valid], table.minute[split.valid], y[split.valid]),
    )


def test_training_is_deterministic() -> None:
    train, valid = parts()
    a = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 7)
    b = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 7)
    assert np.array_equal(a.predict(train[0], train[1]), b.predict(train[0], train[1]))


def test_a_bigger_lead_never_lowers_the_chance() -> None:
    train, valid = parts()
    model = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 0)
    x = np.zeros((41, len(WP_FEATURES)))
    x[:, GOLD] = np.linspace(-10, 10, 41)
    for minute in (5.0, 20.0):
        p = model.predict(x, np.full(41, minute))
        assert (np.diff(p) >= 0).all()
        assert p[-1] > p[0]
