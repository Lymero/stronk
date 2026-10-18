"""Class-level decision points with champion as a confounder (ADR-039)."""

from collections.abc import Callable

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.wpa.pooling import pool_by_class
from stronk_pipeline.domain.wpa.reference import estimate
from stronk_pipeline.domain.wpa.types import WpaSettings

type TableFactory = Callable[..., DecisionTable]


def test_pools_champions_of_a_class_with_indicators(table_factory: TableFactory) -> None:
    table = table_factory(["A", "B", "A"], [1, 0, 1], champions=["Jinx", "Ashe", "Jinx"],
                          champion_class="marksman")  # fmt: skip
    pooled = pool_by_class(table)
    assert set(pooled.table.champion.tolist()) == {"marksman"}
    assert pooled.table.feature_names == ("gold_diff", "champion=Jinx")  # Ashe is the baseline
    jinx = (table.champion[pooled.order] == "Jinx").astype(float)
    assert pooled.table.features[:, 1].tolist() == jinx.tolist()
    assert pooled.strata.tolist() == table.champion[pooled.order].tolist()
    assert pooled.table.outcome.tolist() == table.outcome[pooled.order].tolist()


def test_champion_confounding_is_removed(table_factory: TableFactory) -> None:
    """Jinx buys A far more and wins more; A itself does nothing. Pooled without the champion,
    A looks good; with the champion as a feature, it doesn't."""
    rng = np.random.default_rng(31)
    n = 8000
    jinx = rng.random(n) < 0.5
    chose_a = rng.random(n) < np.where(jinx, 0.75, 0.25)
    win = (rng.random(n) < np.where(jinx, 0.58, 0.42)).astype(int)
    table = table_factory(np.where(chose_a, "A", "B").tolist(), win.tolist(),
                          champions=np.where(jinx, "Jinx", "Ashe").tolist(),
                          champion_class="marksman")  # fmt: skip
    wp = np.full(n, 0.5)
    naive = pool_by_class(table)  # the same pooling, without champion fixed effects
    (a_naive,) = [e for e in estimate(naive.table, wp, WpaSettings()) if e.option == "A"]
    pooled = pool_by_class(table)
    by_champion = estimate(pooled.table, wp[pooled.order], WpaSettings(), strata=pooled.strata)
    (a_pooled,) = [e for e in by_champion if e.option == "A"]
    assert a_naive.wpa is not None
    assert a_naive.wpa > 0.05
    assert a_pooled.wpa is not None
    assert abs(a_pooled.wpa) < 0.02
