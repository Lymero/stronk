import numpy as np

from stronk_pipeline.domain.backtest import backtest
from stronk_pipeline.domain.wpa.types import OptionEstimate


def contrast(
    option: str,
    effect: float,
    *,
    q: float = 0.5,
    half_width: float = 0.05,
    versus: str = "A",
    champion: str = "Champ1",
) -> OptionEstimate:
    return OptionEstimate(
        champion,
        "fighter",
        "TOP",
        0,
        option,
        effect,
        (effect - half_width, effect + half_width),
        400,
        q=q,
        versus=versus,
        contrast=effect,
        contrast_ci=(effect - half_width, effect + half_width),
    )


def most_played() -> OptionEstimate:
    return OptionEstimate("Champ1", "fighter", "TOP", 0, "A", 0.0, (-0.01, 0.01), 900)


def test_pairs_contrasts_by_option_and_versus() -> None:
    earlier = [most_played(), contrast("B", 0.04), contrast("C", -0.02), contrast("D", 0.01)]
    later = [
        most_played(),
        contrast("B", 0.03),
        contrast("C", 0.01),
        contrast("D", 0.02, versus="B"),  # another most played: a different contrast
        contrast("E", 0.05),
    ]
    b = backtest(earlier, later, fdr=0.05)
    assert (b.earlier_contrasts, b.later_contrasts, b.paired) == (3, 4, 2)
    assert b.sign_agreement == 0.5


def test_clear_contrasts_and_claims() -> None:
    earlier = [
        contrast("B", 0.10, q=0.01),  # a claim that holds and stays clear
        contrast("C", -0.08, q=0.04),  # a claim that flips
        contrast("D", 0.07, q=0.2),  # clear interval, not a claim
        contrast("E", 0.06, q=0.01),  # a claim the later patch didn't measure
        contrast("F", 0.01, q=0.9),
    ]
    later = [
        contrast("B", 0.09, q=0.02),
        contrast("C", 0.03, q=0.6),
        contrast("D", 0.02, q=0.7),
        contrast("F", -0.01, q=0.9),
    ]
    b = backtest(earlier, later, fdr=0.05)
    assert b.paired == 4
    assert b.clear == 3
    assert b.clear_sign_agreement is not None
    assert np.isclose(b.clear_sign_agreement, 2 / 3)
    assert [c.key[3] for c in b.claims] == ["B", "C", "E"]
    assert [c.later for c in b.claims] == [0.09, 0.03, None]
    assert (b.claims_held, b.claims_replicated) == (1, 1)


def test_identical_patches_agree_fully() -> None:
    rng = np.random.default_rng(0)
    rows = [contrast(f"O{i}", float(e)) for i, e in enumerate(rng.normal(0, 0.03, 50))]
    b = backtest(rows, rows, fdr=0.05)
    assert b.sign_agreement == 1.0
    assert b.correlation is not None
    assert np.isclose(b.correlation, 1.0)
    assert b.slope is not None
    assert np.isclose(b.slope, 1.0)


def test_noise_alone_agrees_about_half_the_time() -> None:
    rng = np.random.default_rng(1)
    n = 2000
    earlier = [contrast(f"O{i}", float(e)) for i, e in enumerate(rng.normal(0, 0.03, n))]
    later = [contrast(f"O{i}", float(e)) for i, e in enumerate(rng.normal(0, 0.03, n))]
    b = backtest(earlier, later, fdr=0.05)
    assert b.sign_agreement is not None
    assert abs(b.sign_agreement - 0.5) < 0.05
    assert b.slope is not None
    assert abs(b.slope) < 0.1


def test_shared_effects_carry_over_as_their_reliability() -> None:
    """Measured = true + noise of the same size on each patch: about half carries over."""
    rng = np.random.default_rng(2)
    n = 2000
    truth = rng.normal(0, 0.03, n)
    earlier = [
        contrast(f"O{i}", float(t + e))
        for i, (t, e) in enumerate(zip(truth, rng.normal(0, 0.03, n), strict=True))
    ]
    later = [
        contrast(f"O{i}", float(t + e))
        for i, (t, e) in enumerate(zip(truth, rng.normal(0, 0.03, n), strict=True))
    ]
    b = backtest(earlier, later, fdr=0.05)
    assert b.slope is not None
    assert abs(b.slope - 0.5) < 0.06
    # Correlation 0.5 between the two: same sign 1/2 + arcsin(0.5)/pi = 2/3 of the time.
    assert b.sign_agreement is not None
    assert abs(b.sign_agreement - 2 / 3) < 0.03


def test_nothing_paired() -> None:
    b = backtest([contrast("B", 0.1)], [contrast("C", 0.1)], fdr=0.05)
    assert b.paired == 0
    assert b.sign_agreement is None
    assert b.clear_sign_agreement is None
    assert b.correlation is None
    assert b.slope is None
