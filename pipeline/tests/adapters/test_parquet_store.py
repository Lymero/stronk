from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from winprob_builders import frames

from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore, ParquetFrameStore
from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.result import Err, Ok

type TableFactory = Callable[..., DecisionTable]


@pytest.fixture
def written(tmp_path: Path, table_factory: TableFactory) -> Path:
    table = table_factory(["A", "B", "A"], [1, 0, 1], features=np.array([[0.5], [-1.0], [2.0]]))
    result = ParquetDecisionStore().write_decisions(table, tmp_path / "d.parquet")
    assert isinstance(result, Ok)
    return result.value


def test_round_trip(written: Path, table_factory: TableFactory) -> None:
    result = ParquetDecisionStore().read_decisions(written)
    assert isinstance(result, Ok)
    table = result.value
    assert table.option.tolist() == ["A", "B", "A"]
    assert table.feature_names == ("gold_diff",)
    np.testing.assert_allclose(table.features[:, 0], [0.5, -1.0, 2.0])


def test_missing_file_is_not_found(tmp_path: Path) -> None:
    result = ParquetDecisionStore().read_decisions(tmp_path / "nope.parquet")
    assert isinstance(result, Err)
    assert result.error.kind == "not_found"


def corrupt(path: Path, change: Callable[[pl.DataFrame], pl.DataFrame]) -> Path:
    change(pl.read_parquet(path)).write_parquet(path)
    return path


type Change = Callable[[pl.DataFrame], pl.DataFrame]
CORRUPTIONS: list[tuple[Change, str]] = [
    (lambda f: f.drop("outcome"), "lacks columns"),
    (lambda f: f.with_columns(outcome=pl.lit(3, pl.Int64)), "outcome"),
    (lambda f: f.with_columns(slot=pl.lit("x")), "slot"),
    (lambda f: f.with_columns(f_gold_diff=pl.lit(None, pl.Float64)), "null"),
]


@pytest.mark.parametrize(("change", "message"), CORRUPTIONS)
def test_invalid_contents_are_rejected(
    written: Path, change: Callable[[pl.DataFrame], pl.DataFrame], message: str
) -> None:
    result = ParquetDecisionStore().read_decisions(corrupt(written, change))
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
    assert message in result.error.message


def test_non_parquet_file_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "d.parquet"
    path.write_text("not parquet")
    result = ParquetDecisionStore().read_decisions(path)
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"


def test_frames_round_trip(tmp_path: Path) -> None:
    table = frames(3, minutes=4)
    store = ParquetFrameStore()
    assert store.write_frames(table, tmp_path / "f.parquet") == Ok(tmp_path / "f.parquet")
    read = store.read_frames(tmp_path / "f.parquet")
    assert isinstance(read, Ok)
    assert set(read.value.feature_names) == set(table.feature_names)
    assert np.array_equal(read.value.match_id, table.match_id)
    assert np.array_equal(read.value.outcome, table.outcome)


def test_frames_without_required_columns_are_invalid(tmp_path: Path) -> None:
    pl.DataFrame({"match_id": ["a"]}).write_parquet(tmp_path / "f.parquet")
    result = ParquetFrameStore().read_frames(tmp_path / "f.parquet")
    assert isinstance(result, Err)
    assert "lacks columns" in result.error.message
