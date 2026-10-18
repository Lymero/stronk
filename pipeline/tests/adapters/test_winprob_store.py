import json
from pathlib import Path

import numpy as np
import pytest
from winprob_builders import frames

from stronk_pipeline.adapters.lightgbm_winprob import LightGbmLearner
from stronk_pipeline.adapters.winprob_store import JsonWinProbStore
from stronk_pipeline.domain.result import Err, Ok
from stronk_pipeline.domain.winprob import (
    WP_FEATURES,
    WP_MONOTONE,
    LogisticLearner,
    columns,
    split_by_match,
)
from stronk_pipeline.ports import WinProbLearner


@pytest.mark.parametrize(
    "learner", [LogisticLearner(), LightGbmLearner()], ids=lambda learner: learner.id
)
def test_round_trip_predicts_the_same(learner: WinProbLearner, tmp_path: Path) -> None:
    table = frames(120, seed=2)
    x = columns(table.features, table.feature_names, WP_FEATURES)
    y = table.outcome.astype(np.float64)
    split = split_by_match(table.match_id)
    train = (x[split.train], table.minute[split.train], y[split.train])
    valid = (x[split.valid], table.minute[split.valid], y[split.valid])
    model = learner.fit(train, valid, WP_FEATURES, WP_MONOTONE, 0)
    store = JsonWinProbStore()
    assert store.save(model, tmp_path / "m.json") == Ok(tmp_path / "m.json")
    loaded = store.load(tmp_path / "m.json")
    assert isinstance(loaded, Ok)
    assert loaded.value.feature_names == WP_FEATURES
    assert np.allclose(loaded.value.predict(x, table.minute), model.predict(x, table.minute))


def test_missing_model_is_not_found(tmp_path: Path) -> None:
    result = JsonWinProbStore().load(tmp_path / "nope.json")
    assert isinstance(result, Err)
    assert result.error.kind == "not_found"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"kind": "logistic"}),
        json.dumps({"kind": "logistic", "features": ["a"]}),
        json.dumps({"kind": "logistic", "features": ["a"], "mean": [0], "scale": [1], "coef": [0]}),
        json.dumps({"kind": "lightgbm", "features": ["a"], "booster": "garbage"}),
        json.dumps({"kind": "lightgbm", "features": ["a"], "booster": 3}),
        json.dumps({"kind": "forest", "features": ["a"]}),
        json.dumps({"kind": "logistic", "features": [1]}),
    ],
)
def test_bad_model_files_are_invalid(content: str, tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text(content)
    result = JsonWinProbStore().load(tmp_path / "m.json")
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
