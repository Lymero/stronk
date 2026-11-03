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


def test_a_table_written_in_parts_reads_whole(tmp_path: Path, table_factory: TableFactory) -> None:
    """ADR-080: extract writes a chunk of games at a time; part 0 replaces the old table."""
    store, path = ParquetDecisionStore(), tmp_path / "d.parquet"
    assert isinstance(store.write_decisions(table_factory(["Z"], [0]), path), Ok)  # a whole file
    first = table_factory(["A", "B"], [1, 0], champions=["Ahri", "Zed"])
    second = table_factory(["C"], [1], champions=["Ahri"], match_ids=["M9"])
    for part, table in enumerate((first, second)):
        assert isinstance(store.write_decisions(table, path, part), Ok)
    assert sorted(p.name for p in path.iterdir()) == ["part-00000.parquet", "part-00001.parquet"]
    read = store.read_decisions(path)
    assert isinstance(read, Ok)
    assert read.value.option.tolist() == ["A", "C", "B"]  # canonical order: Ahri, then Zed


def test_decisions_read_a_few_picks_at_a_time(tmp_path: Path, table_factory: TableFactory) -> None:
    store, path = ParquetDecisionStore(), tmp_path / "d.parquet"
    table = table_factory(
        ["A", "B", "C", "D"], [1, 0, 1, 0], champions=["Zed", "Ahri", "Zed", "Lux"]
    )
    assert isinstance(store.write_decisions(table, path, 0), Ok)
    picks = store.picks(path)
    assert isinstance(picks, Ok)
    assert [(p.champion, p.role, p.rows) for p in picks.value] == [
        ("Ahri", "MIDDLE", 1),
        ("Lux", "MIDDLE", 1),
        ("Zed", "MIDDLE", 2),
    ]
    zed = store.read_decisions(path, [("Zed", "MIDDLE")])
    assert isinstance(zed, Ok)
    assert zed.value.option.tolist() == ["A", "C"]  # in the table's order
    none = store.read_decisions(path, [("Zed", "TOP")])
    assert isinstance(none, Ok)
    assert len(none.value) == 0


def test_tables_are_never_read_with_prefiltered_decoding(
    tmp_path: Path, table_factory: TableFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: Polars 2.0's pre-filtered decode, its default when a filter drops rows, now and
    # then misread a value or corrupted memory under load (runs/polars-prefilter). Not
    # reproducible in a test, so the scan's option is checked instead.
    store, path = ParquetDecisionStore(), tmp_path / "d.parquet"
    assert isinstance(store.write_decisions(table_factory(["A", "B"], [1, 0]), path, 0), Ok)
    asked: list[object] = []
    scan = pl.scan_parquet

    def recording(source: Path, **options: object) -> pl.LazyFrame:
        asked.append(options.get("parallel", "auto"))
        return scan(source, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(pl, "scan_parquet", recording)
    assert isinstance(store.read_decisions(path, [("Zed", "MIDDLE")]), Ok)
    assert isinstance(store.picks(path), Ok)
    assert asked == ["row_groups", "row_groups"]  # both scans
