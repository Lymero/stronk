from collections.abc import Callable
from pathlib import Path

import numpy as np

from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.application.wpa_estimate import (
    WpaEstimateParams,
    WpaEstimateResult,
    wpa_estimate_command,
)
from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.result import Err, Ok, Result
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
    command = wpa_estimate_command(store, {"v1-reference": ReferenceEstimatorV1()})
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
