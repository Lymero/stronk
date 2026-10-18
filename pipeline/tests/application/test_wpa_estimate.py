from collections.abc import Callable
from pathlib import Path

import numpy as np

from stronk_pipeline.adapters.winprob_store import JsonWinProbStore
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.application.wpa_estimate import (
    WpaEstimateParams,
    WpaEstimateResult,
    wpa_estimate_command,
)
from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import fit_logistic
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import LogisticWinProb
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1
from stronk_pipeline.ports import StoreError

type TableFactory = Callable[..., DecisionTable]


class FakeStore:
    def __init__(self, tables: dict[str, DecisionTable]) -> None:
        self.tables = tables

    def read_decisions(self, path: Path) -> Result[DecisionTable, StoreError]:
        table = self.tables.get(str(path))
        return Ok(table) if table is not None else Err(StoreError("not_found", str(path)))

    def write_decisions(self, table: DecisionTable, path: Path) -> Result[Path, StoreError]:
        self.tables[str(path)] = table
        return Ok(path)


def run(store: FakeStore, **params: object) -> Result[WpaEstimateResult, CommandError]:
    estimators = {"v1-reference": ReferenceEstimatorV1()}
    command = wpa_estimate_command(store, estimators, JsonWinProbStore())
    return command.run(WpaEstimateParams.model_validate({"bootstrap_samples": 20, **params}))


def test_estimates_every_option(table_factory: TableFactory) -> None:
    rng = np.random.default_rng(0)
    n = 200
    table = table_factory(
        np.where(rng.random(n) < 0.5, "A", "B").tolist(),
        (rng.random(n) < 0.5).astype(int).tolist(),
        features=rng.normal(size=(n, 1)),
    )
    result = run(FakeStore({"d.parquet": table}), decisions="d.parquet")
    assert isinstance(result, Ok)
    assert [e.option for e in result.value.estimates] == ["A", "B"]
    assert result.value.decisions == n


def test_missing_table_is_not_found() -> None:
    result = run(FakeStore({}), decisions="missing.parquet")
    assert isinstance(result, Err)
    assert result.error.code == "not_found"


def test_unknown_estimator_is_invalid_params(table_factory: TableFactory) -> None:
    store = FakeStore({"d.parquet": table_factory(["A"], [1])})
    result = run(store, decisions="d.parquet", estimator="v9")
    assert isinstance(result, Err)
    assert result.error.code == "invalid_params"


def test_uses_a_trained_model_by_feature_name(table_factory: TableFactory, tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    n = 200
    table = table_factory(
        np.where(rng.random(n) < 0.5, "A", "B").tolist(),
        (rng.random(n) < 0.5).astype(int).tolist(),
        features=rng.normal(size=(n, 1)),
    )
    name = table.feature_names[0]
    x = rng.normal(size=(50, 3))  # inputs: lead, minute, lead x minute
    model = LogisticWinProb((name,), fit_logistic(x, (x[:, 0] > 0).astype(np.float64)))
    JsonWinProbStore().save(model, tmp_path / "m.json")
    store = FakeStore({"d.parquet": table})
    result = run(store, decisions="d.parquet", winprob=str(tmp_path / "m.json"))
    assert isinstance(result, Ok)
    assert result.value.decisions == n


def test_model_needing_absent_features_is_invalid_input(
    table_factory: TableFactory, tmp_path: Path
) -> None:
    x = np.random.default_rng(0).normal(size=(50, 3))
    model = LogisticWinProb(("no_such_feature",), fit_logistic(x, (x[:, 0] > 0).astype(np.float64)))
    JsonWinProbStore().save(model, tmp_path / "m.json")
    store = FakeStore({"d.parquet": table_factory(["A"], [1])})
    result = run(store, decisions="d.parquet", winprob=str(tmp_path / "m.json"))
    assert isinstance(result, Err)
    assert "no_such_feature" in result.error.message


def test_missing_model_is_not_found(table_factory: TableFactory, tmp_path: Path) -> None:
    store = FakeStore({"d.parquet": table_factory(["A"], [1])})
    result = run(store, decisions="d.parquet", winprob=str(tmp_path / "nope.json"))
    assert isinstance(result, Err)
    assert result.error.code == "not_found"
