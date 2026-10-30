from collections.abc import Callable

import numpy as np
import pytest

from stronk_pipeline.domain.decisions import DecisionTable, InvalidDecisionsError

type TableFactory = Callable[..., DecisionTable]


def test_rows_are_sorted_canonically(table_factory: TableFactory) -> None:
    table = table_factory(["A", "B", "C"], [1, 0, 1], match_ids=["M3", "M1", "M2"])
    assert table.match_id.tolist() == ["M1", "M2", "M3"]
    assert table.option.tolist() == ["B", "C", "A"]


def test_duplicate_decisions_count_once(table_factory: TableFactory) -> None:
    table = table_factory(["A", "A", "B"], [1, 1, 0], match_ids=["M1", "M1", "M2"])
    assert len(table) == 2


def test_a_players_late_items_share_a_slot_and_all_count() -> None:
    # Two late items of one player (ADR-067), and the first again from a duplicated match.
    table = DecisionTable.create(
        match_id=np.array(["M1", "M1", "M1"]),
        participant=np.ones(3, dtype=np.int64),
        champion=np.array(["Jinx"] * 3),
        champion_class=np.array(["marksman"] * 3),
        role=np.array(["BOTTOM"] * 3),
        slot=np.full(3, 4, dtype=np.int64),
        minute=np.array([31.0, 24.0, 24.0]),
        option=np.array(["3031", "3033", "3033"]),
        outcome=np.ones(3, dtype=np.int64),
        features=np.zeros((3, 1)),
        feature_names=("gold_diff",),
    )
    assert table.option.tolist() == ["3033", "3031"]
    assert table.minute.tolist() == [24.0, 31.0]


def test_decision_points_partition_rows(table_factory: TableFactory) -> None:
    table = table_factory(["A", "B", "A"], [1, 0, 1], champions=["Zed", "Ahri", "Zed"])
    points = dict(table.decision_points())
    assert sorted(points) == [("Ahri", "MIDDLE", 1), ("Zed", "MIDDLE", 1)]
    assert sorted(np.concatenate(list(points.values())).tolist()) == [0, 1, 2]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"outcome": np.array([2], dtype=np.int64)}, "outcome"),
        ({"features": np.array([[np.nan]])}, "finite"),
        ({"features": np.zeros((1, 2))}, "shape"),
        ({"slot": np.array([-1], dtype=np.int64)}, "slot"),
        ({"role": np.array(["TOP", "TOP"])}, "equal length"),
        ({"feature_names": ("x", "x"), "features": np.zeros((1, 2))}, "unique"),
    ],
)
def test_invalid_tables_are_rejected(change: dict[str, object], message: str) -> None:
    columns: dict[str, object] = {
        "match_id": np.array(["M1"]),
        "participant": np.array([1], dtype=np.int64),
        "champion": np.array(["Ahri"]),
        "champion_class": np.array(["mage"]),
        "role": np.array(["MIDDLE"]),
        "slot": np.array([1], dtype=np.int64),
        "minute": np.array([10.0]),
        "option": np.array(["A"]),
        "outcome": np.array([1], dtype=np.int64),
        "features": np.zeros((1, 1)),
        "feature_names": ("gold_diff",),
    }
    columns.update(change)
    with pytest.raises(InvalidDecisionsError, match=message):
        DecisionTable.create(**columns)  # pyright: ignore[reportArgumentType]
