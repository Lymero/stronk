import re

import lightgbm as lgb
import numpy as np
import pytest
from winprob_builders import GOLD, frames

from stronk_pipeline.adapters.lightgbm_winprob import (
    EARLY_STOPPING,
    MAX_ROUNDS,
    MINUTE,
    PARAMS,
    LightGbmLearner,
    LightGbmWinProb,
    data_seed,
)
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.winprob import WP_FEATURES, WP_MONOTONE, Rows, columns, split_by_match

type Part = tuple[Floats, Floats, Floats]


def arrays(matches: int = 300) -> tuple[Part, Part]:
    table = frames(matches, seed=5)
    x = columns(table.features, table.feature_names, WP_FEATURES)
    y = table.outcome.astype(np.float64)
    split = split_by_match(table.match_id)
    return (
        (x[split.train], table.minute[split.train], y[split.train]),
        (x[split.valid], table.minute[split.valid], y[split.valid]),
    )


def parts(matches: int = 300) -> tuple[Rows, Rows]:
    train, valid = arrays(matches)
    return Rows.of(*train), Rows.of(*valid)


def chunked(part: Part, size: int) -> Rows:
    x, minute, y = part
    starts = range(0, len(y), size)
    return Rows(
        tuple(len(y[s : s + size]) for s in starts),
        lambda i: (
            x[i * size : (i + 1) * size],
            minute[i * size : (i + 1) * size],
            y[i * size : (i + 1) * size],
        ),
    )


def test_training_is_deterministic() -> None:
    train, valid = parts()
    a = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 7)
    b = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 7)
    x, minute, _ = train.load(0)
    assert np.array_equal(a.predict(x, minute), b.predict(x, minute))


def text(model: object) -> str:
    assert isinstance(model, LightGbmWinProb)
    return str(model.booster.model_to_string())


def test_rows_read_a_chunk_at_a_time_give_the_model_of_one_array() -> None:
    """ADR-081: frames stream to LightGBM in chunks, and the model is the one LightGBM builds
    from every row in one array with the same parameters, byte for byte."""
    train, valid = arrays(2000)
    whole = LightGbmLearner().fit(Rows.of(*train), Rows.of(*valid), WP_FEATURES, WP_MONOTONE, 0)
    streamed = LightGbmLearner().fit(
        chunked(train, 997), chunked(valid, 501), WP_FEATURES, WP_MONOTONE, 0
    )
    assert text(streamed) == text(whole)
    # As trained before ADR-081: arrays, `seed` alone, LightGBM deriving the sampling seed.
    params = {**PARAMS, "seed": 0, "monotone_constraints": [*WP_MONOTONE, 0]}
    inputs = [*WP_FEATURES, MINUTE]
    train_set = lgb.Dataset(np.column_stack(train[:2]), label=train[2], feature_name=inputs)
    valid_set = lgb.Dataset(np.column_stack(valid[:2]), label=valid[2], reference=train_set)
    before = lgb.train(  # pyright: ignore[reportUnknownMemberType]
        params,
        train_set,
        num_boost_round=MAX_ROUNDS,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
    )
    x, minute, _ = valid
    assert np.array_equal(
        LightGbmWinProb(before, WP_FEATURES).predict(x, minute), streamed.predict(x, minute)
    )


@pytest.mark.parametrize("seed", [0, 1, 7, 12345, 2**31 - 1])
def test_the_sampling_seed_is_the_one_lightgbm_derives(seed: int) -> None:
    rng = np.random.default_rng(0)
    data = lgb.Dataset(rng.normal(size=(100, 2)), label=np.r_[np.zeros(50), np.ones(50)])
    booster = lgb.train(  # pyright: ignore[reportUnknownMemberType]
        {"objective": "binary", "verbosity": -1, "seed": seed}, data, num_boost_round=1
    )
    found = re.search(r"\[data_random_seed: (-?\d+)\]", str(booster.model_to_string()))
    assert found is not None
    assert data_seed(seed) == int(found.group(1))


def test_a_bigger_lead_never_lowers_the_chance() -> None:
    train, valid = parts()
    model = LightGbmLearner().fit(train, valid, WP_FEATURES, WP_MONOTONE, 0)
    x = np.zeros((41, len(WP_FEATURES)))
    x[:, GOLD] = np.linspace(-10, 10, 41)
    for minute in (5.0, 20.0):
        p = model.predict(x, np.full(41, minute))
        assert (np.diff(p) >= 0).all()
        assert p[-1] > p[0]
