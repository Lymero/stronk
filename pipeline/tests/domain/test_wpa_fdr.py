"""Benjamini-Hochberg false discovery rate control (ADR-036)."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from stronk_pipeline.domain.wpa.fdr import benjamini_hochberg, two_sided_p


def test_matches_the_textbook_example() -> None:
    # Benjamini & Hochberg (1995), the 15 p-values of their worked example.
    p = np.array([0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344,
                  0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.0])  # fmt: skip
    rejected = benjamini_hochberg(p) <= 0.05
    assert rejected.sum() == 4  # the paper rejects the four smallest


@given(st.lists(st.floats(0.0, 1.0), min_size=1, max_size=60))
def test_q_values_are_bounded_and_keep_the_order_of_p(values: list[float]) -> None:
    p = np.array(values)
    q = benjamini_hochberg(p)
    assert ((q >= p - 1e-12) & (q <= 1.0)).all()  # p * m / m can round one ulp down
    order = np.argsort(p, kind="stable")
    assert (np.diff(q[order]) >= -1e-12).all()


def test_q_values_do_not_depend_on_order() -> None:
    p = np.random.default_rng(1).random(50)
    perm = np.random.default_rng(2).permutation(50)
    assert benjamini_hochberg(p[perm]) == pytest.approx(benjamini_hochberg(p)[perm])


def test_under_the_null_few_are_rejected() -> None:
    p = np.random.default_rng(3).random(10_000)
    assert (p <= 0.05).sum() > 400  # unadjusted: about 500 false positives
    assert (benjamini_hochberg(p) <= 0.05).sum() <= 5


def test_two_sided_p() -> None:
    assert two_sided_p(1.96, 1.0) == pytest.approx(0.05, abs=1e-3)
    assert two_sided_p(-1.96, 1.0) == pytest.approx(0.05, abs=1e-3)
    assert two_sided_p(0.1, 0.0) == 1.0
    assert two_sided_p(float("nan"), 1.0) == 1.0
