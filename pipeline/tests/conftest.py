from collections.abc import Callable, Sequence

import numpy as np
import pytest

from stronk_pipeline.domain.decisions import DecisionTable

type TableFactory = Callable[..., DecisionTable]


def make_table(
    options: Sequence[str],
    outcomes: Sequence[int],
    *,
    match_ids: Sequence[str] | None = None,
    champions: Sequence[str] | None = None,
    champion_class: str = "fighter",
    slot: int = 1,
    features: np.ndarray | None = None,
) -> DecisionTable:
    n = len(options)
    return DecisionTable.create(
        match_id=np.array(match_ids if match_ids is not None else [f"M{i}" for i in range(n)]),
        participant=np.ones(n, dtype=np.int64),
        champion=np.array(champions if champions is not None else ["Ahri"] * n),
        champion_class=np.full(n, champion_class),
        role=np.full(n, "MIDDLE"),
        slot=np.full(n, slot, dtype=np.int64),
        minute=np.full(n, 10.0),
        option=np.array(options),
        outcome=np.array(outcomes, dtype=np.int64),
        features=features if features is not None else np.zeros((n, 1)),
        feature_names=("gold_diff",),
    )


@pytest.fixture
def table_factory() -> TableFactory:
    return make_table
