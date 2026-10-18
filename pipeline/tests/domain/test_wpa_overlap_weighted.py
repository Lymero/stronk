"""Overlap-weighted WPA (ADR-037): it removes v1's attenuation of situational choices."""

from collections.abc import Callable

import numpy as np
import pytest

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats, expit
from stronk_pipeline.domain.wpa.overlap_weighted import OverlapWeightedEstimator, overlap_weighted
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1, estimate
from stronk_pipeline.domain.wpa.types import WpaSettings
from stronk_pipeline.ports import Estimator

type TableFactory = Callable[..., DecisionTable]


def situational(table_factory: TableFactory, n: int = 40_000) -> tuple[DecisionTable, Floats]:
    """A adds +10% everywhere and is chosen more when ahead. WP is exact for how people play:
    0.5 + 0.1 P(A | x), so the only bias left is the estimator's own."""
    rng = np.random.default_rng(21)
    gold = rng.normal(size=n)
    p_a = expit(1.5 * gold)
    chose_a = rng.random(n) < p_a
    win = (rng.random(n) < 0.5 + 0.1 * chose_a).astype(int)
    table = table_factory(np.where(chose_a, "A", "B").tolist(), win.tolist(),
                          features=gold[:, None])  # fmt: skip
    # The table puts rows in canonical order, so WP is computed from its own rows.
    return table, 0.5 + 0.1 * expit(1.5 * table.features[:, 0])


def a_effect(table: DecisionTable, wp: Floats, estimator: Estimator) -> float:
    (a,) = [e for e in estimator.estimate(table, wp, WpaSettings()) if e.option == "A"]
    assert a.wpa is not None
    return a.wpa


def test_recovers_a_situational_choice_that_v1_attenuates(table_factory: TableFactory) -> None:
    table, wp = situational(table_factory)
    assert a_effect(table, wp, OverlapWeightedEstimator()) == pytest.approx(0.10, abs=0.015)
    assert a_effect(table, wp, ReferenceEstimatorV1()) == pytest.approx(0.07, abs=0.015)


def test_agrees_with_v1_when_the_situation_does_not_drive_the_choice(
    table_factory: TableFactory,
) -> None:
    rng = np.random.default_rng(22)
    n = 20_000
    chose_a = rng.random(n) < 0.4
    win = (rng.random(n) < 0.5 + 0.05 * chose_a).astype(int)
    table = table_factory(np.where(chose_a, "A", "B").tolist(), win.tolist(),
                          features=rng.normal(size=(n, 1)))  # fmt: skip
    wp = np.full(n, 0.52)
    ow = a_effect(table, wp, OverlapWeightedEstimator())
    v1 = a_effect(table, wp, ReferenceEstimatorV1())
    assert ow == pytest.approx(v1, abs=0.003)


def test_is_registered_through_the_shared_pipeline(table_factory: TableFactory) -> None:
    table, wp = situational(table_factory, 4000)
    via_class = OverlapWeightedEstimator().estimate(table, wp, WpaSettings())
    assert via_class == estimate(table, wp, WpaSettings(), overlap_weighted)
