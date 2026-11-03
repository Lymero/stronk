from typing import Any

import numpy as np
import pytest
from compare_estimates import choose, compare
from wp_models import FEATURES, Frames, designs, rcs


def option(name: str, chosen: int, **rest: Any) -> dict[str, Any]:
    return {
        "option": name,
        "n": chosen,
        "chosen": chosen,
        "wpa": 0.0,
        "flags": [],
        "versus": None,
        "contrast": None,
        "contrast_ci": None,
        "q": None,
        **rest,
    }


def against(
    name: str, chosen: int, contrast: float, half_width: float, **rest: Any
) -> dict[str, Any]:
    ci = [contrast - half_width, contrast + half_width]
    rest.setdefault("flags", ["no_clear_difference"])
    return option(name, chosen, versus="1", contrast=contrast, contrast_ci=ci, **rest)


def test_the_most_played_option_without_a_bet() -> None:
    assert choose([option("1", 300), option("2", 100)]) == ("1", "popular")


def test_a_precise_gain_is_the_best_bet() -> None:
    # se 0.005: shrunk 0.01 x 0.0004 / 0.000425 = 0.0094
    rows = [option("1", 300), against("2", 200, 0.01, 0.0098)]
    assert choose(rows) == ("2", "best_bet")


def test_a_noisy_gain_shrinks_below_the_line() -> None:
    # se 0.05: shrunk 0.03 x 0.0004 / 0.0029 = 0.0041
    rows = [option("1", 300), against("2", 20, 0.03, 0.098)]
    assert choose(rows) == ("1", "popular")


def test_a_clear_gain_is_clearly_better() -> None:
    rows = [option("1", 300), against("2", 200, 0.02, 0.0098, flags=[])]
    assert choose(rows) == ("2", "clearly_better")


@pytest.mark.parametrize("flag", ["low_sample", "low_overlap"])
def test_too_few_games_never_bet(flag: str) -> None:
    rows = [option("1", 300), against("2", 200, 0.02, 0.0098, flags=[flag])]
    assert choose(rows) == ("1", "popular")


def test_only_comparisons_with_the_most_played_count() -> None:
    rows = [option("1", 300), {**against("2", 200, 0.02, 0.0098), "versus": "3"}]
    assert choose(rows) == ("1", "popular")


def test_identical_files_change_nothing() -> None:
    rows = [option("1", 300), against("2", 200, 0.01, 0.0098)]
    est = {("A", "TOP", 1, r["option"]): r for r in rows}
    lines = compare(est, est)
    assert "import changes: 0 slots choose another option, 0 relabelled" in lines


def test_the_spline_is_linear_beyond_its_outer_knots() -> None:
    knots = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    x = np.array([5.0, 6.0, 7.0, -3.0, -2.0, -1.0])
    basis = rcs(x, knots)
    right, left = basis[:3], basis[3:]
    assert np.allclose(np.diff(right, 2, axis=0), 0.0)
    assert np.allclose(np.diff(left, 2, axis=0), 0.0)


def test_the_pair_terms_flip_with_the_side() -> None:
    """Pairs that didn't would be cancelled by the symmetric prediction (ADR-030)."""
    rng = np.random.default_rng(0)
    n, k = 200, len(FEATURES)
    frames = Frames(
        x=rng.normal(size=(n, k)),
        minute=rng.uniform(5, 40, size=n),
        outcome=(rng.random(n) < 0.5).astype(np.float64),
        match=np.arange(n, dtype=np.intp),
        part=np.zeros(n, dtype=np.int64),
    )
    design = designs(frames)["gam-odd-pairs"]
    x, m = frames.x, frames.minute
    pairs = 2 * (k - 1)
    assert np.allclose(design(-x, m)[:, -pairs:], -design(x, m)[:, -pairs:])
