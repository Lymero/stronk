"""WPA v1 reference: required properties (docs/wpa-method.md, section 8.5) and flag rules."""

from collections.abc import Callable

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.wpa.reference import estimate, event_scores
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate, WpaSettings

type TableFactory = Callable[..., DecisionTable]

FAST = WpaSettings(bootstrap_samples=50, min_decisions=20)


def by_option(estimates: list[OptionEstimate]) -> dict[str, OptionEstimate]:
    return {e.option: e for e in estimates}


def random_decisions(table_factory: TableFactory, n: int, seed: int) -> DecisionTable:
    rng = np.random.default_rng(seed)
    gold = rng.normal(size=(n, 1))
    options = np.where(rng.random(n) < 0.5, "A", "B").tolist()
    outcomes = (rng.random(n) < 0.5).astype(int).tolist()
    return table_factory(options, outcomes, features=gold)


# The factory fixture is stateless, so sharing it across Hypothesis examples is safe.
REUSE_FIXTURE = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@REUSE_FIXTURE
@given(
    outcomes=st.lists(st.integers(0, 1), min_size=1, max_size=50),
    wp=st.lists(st.floats(0.0, 1.0), min_size=50, max_size=50),
)
def test_event_scores_lie_in_unit_interval(
    table_factory: TableFactory, outcomes: list[int], wp: list[float]
) -> None:
    table = table_factory(["A"] * len(outcomes), outcomes)
    scores = event_scores(table, np.array(wp[: len(table)]))
    assert ((scores >= -1.0) & (scores <= 1.0)).all()


@settings(REUSE_FIXTURE, max_examples=10, deadline=None)
@given(seed=st.integers(0, 2**16))
def test_results_do_not_depend_on_row_order(table_factory: TableFactory, seed: int) -> None:
    table = random_decisions(table_factory, 400, seed)
    order = np.random.default_rng(seed).permutation(len(table))
    shuffled = DecisionTable.create(
        **{f: getattr(table, f)[order] for f in ("match_id", "participant", "champion",
           "champion_class", "role", "slot", "minute", "option", "outcome", "features")},
        feature_names=table.feature_names,
    )  # fmt: skip
    wp = np.full(len(table), 0.5)
    assert estimate(table, wp, FAST) == estimate(shuffled, wp, FAST)


def test_duplicated_matches_do_not_change_results(table_factory: TableFactory) -> None:
    table = random_decisions(table_factory, 400, 3)
    doubled = DecisionTable.create(
        **{f: np.concatenate([getattr(table, f)] * 2) for f in ("match_id", "participant",
           "champion", "champion_class", "role", "slot", "minute", "option", "outcome")},
        features=np.vstack([table.features] * 2),
        feature_names=table.feature_names,
    )  # fmt: skip
    wp = np.full(len(table), 0.5)
    assert estimate(table, wp, FAST) == estimate(doubled, np.full(len(doubled), 0.5), FAST)


def test_effect_is_difference_of_mean_scores(table_factory: TableFactory) -> None:
    # A wins 3 of 4, B wins 1 of 4, WP 0.5 everywhere: effect of A = 0.25 - (-0.25) = 0.5.
    table = table_factory(["A"] * 4 + ["B"] * 4, [1, 1, 1, 0, 1, 0, 0, 0])
    settings = WpaSettings(bootstrap_samples=20, min_estimate_decisions=1)
    estimates = by_option(estimate(table, np.full(8, 0.5), settings))
    assert estimates["A"].wpa == pytest.approx(0.5)
    assert estimates["B"].wpa == pytest.approx(-0.5)


def test_single_option_has_no_comparison_group(table_factory: TableFactory) -> None:
    table = table_factory(["A"] * 10, [1, 0] * 5)
    (only,) = estimate(table, np.full(10, 0.5), FAST)
    assert only.wpa is None
    assert only.flags == {Flag.LOW_OVERLAP}


def test_small_samples_are_flagged(table_factory: TableFactory) -> None:
    table = table_factory(["A", "B"] * 10, [1, 0] * 10)
    estimates = estimate(table, np.full(20, 0.5), WpaSettings(bootstrap_samples=20))
    assert all(Flag.LOW_SAMPLE in e.flags for e in estimates)


def test_a_handful_of_decisions_gets_no_number(table_factory: TableFactory) -> None:
    """Regression: one decision against one gave WPA 1.0 with the interval [1.0, 1.0]."""
    table = table_factory(["A", "B"], [1, 0], match_ids=["M1", "M2"])
    for e in estimate(table, np.full(2, 0.5), WpaSettings(bootstrap_samples=20)):
        assert e.wpa is None
        assert e.ci is None
        assert e.flags == {Flag.LOW_SAMPLE}


def test_overlapping_intervals_are_flagged_unclear(table_factory: TableFactory) -> None:
    table = random_decisions(table_factory, 400, 5)
    estimates = estimate(table, np.full(len(table), 0.5), FAST)
    assert all(Flag.NO_CLEAR_DIFFERENCE in e.flags for e in estimates)


def test_clear_winner_is_not_flagged(table_factory: TableFactory) -> None:
    table = table_factory(["A"] * 200 + ["B"] * 200, [1] * 180 + [0] * 20 + [1] * 20 + [0] * 180)
    estimates = estimate(table, np.full(400, 0.5), FAST)
    assert all(Flag.NO_CLEAR_DIFFERENCE not in e.flags for e in estimates)


def test_estimates_shrink_toward_the_class_mean(table_factory: TableFactory) -> None:
    rng = np.random.default_rng(11)
    champions: list[str] = []
    options: list[str] = []
    outcomes: list[int] = []
    for champion, n in (("Aatrox", 4000), ("Darius", 4000), ("Garen", 4000), ("Sett", 150)):
        champions += [champion] * n
        options += np.where(rng.random(n) < 0.5, "A", "B").tolist()
        outcomes += (rng.random(n) < 0.5).astype(int).tolist()
    match_ids = [f"M{i}" for i in range(len(options))]
    table = table_factory(options, outcomes, champions=champions, match_ids=match_ids)
    wp = np.full(len(table), 0.5)
    raw = estimate(table, wp, WpaSettings(min_shrinkage_group=99))
    shrunk = estimate(table, wp, WpaSettings())

    def sett_a(estimates: list[OptionEstimate]) -> float:
        (e,) = [e for e in estimates if e.champion == "Sett" and e.option == "A"]
        assert e.wpa is not None
        return e.wpa

    assert abs(sett_a(shrunk)) < abs(sett_a(raw))


def test_fully_shrunk_estimates_keep_an_interval(table_factory: TableFactory) -> None:
    """Regression: shrinking interval ends like the estimate collapsed them to a point when the
    champions' effects were indistinguishable (seen on the corpus: Yone mid, Fleet Footwork)."""
    rng = np.random.default_rng(12)
    champions: list[str] = []
    options: list[str] = []
    outcomes: list[int] = []
    for champion in ("Aatrox", "Darius", "Garen"):
        champions += [champion] * 600
        options += np.where(rng.random(600) < 0.5, "A", "B").tolist()
        outcomes += (rng.random(600) < 0.5).astype(int).tolist()
    match_ids = [f"M{i}" for i in range(len(options))]
    table = table_factory(options, outcomes, champions=champions, match_ids=match_ids)
    for e in estimate(table, np.full(len(table), 0.5), WpaSettings()):
        assert e.wpa is not None
        assert e.ci is not None
        assert e.ci[0] < e.wpa < e.ci[1]
        assert e.ci[1] - e.ci[0] > 0.02  # about 2 x 1.96 x the prior's standard error


def test_rejects_wp_outside_unit_interval(table_factory: TableFactory) -> None:
    table = table_factory(["A", "B"], [1, 0])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        estimate(table, np.array([0.5, 1.5]))


def test_a_rare_option_does_not_remove_the_others_numbers(table_factory: TableFactory) -> None:
    """Regression: overlap required every option's propensity >= epsilon, so one option seen a
    handful of times emptied the overlap population, and more games gave fewer numbers."""
    rng = np.random.default_rng(5)
    options = np.where(rng.random(1000) < 0.5, "A", "B").tolist() + ["C"] * 3
    outcomes = (rng.random(len(options)) < 0.5).astype(int).tolist()
    table = table_factory(options, outcomes, features=rng.normal(size=(len(options), 1)))
    estimates = by_option(estimate(table, np.full(len(table), 0.5), FAST))
    assert estimates["A"].wpa is not None
    assert estimates["B"].wpa is not None
    assert estimates["C"].wpa is None
    assert Flag.LOW_OVERLAP in estimates["C"].flags


def test_clear_needs_to_survive_false_discovery_control(table_factory: TableFactory) -> None:
    """Among many champions with no effect, some contrasts look significant on their own; after
    Benjamini-Hochberg across the run, none of them is called clear."""
    rng = np.random.default_rng(8)
    champions = [f"C{i}" for i in range(60) for _ in range(1500)]
    options = rng.choice(["A", "B", "C"], size=len(champions), p=[0.4, 0.33, 0.27]).tolist()
    outcomes = (rng.random(len(champions)) < 0.5).astype(int).tolist()
    table = table_factory(options, outcomes, champions=champions,
                          match_ids=[f"M{i}" for i in range(len(champions))])  # fmt: skip
    estimates = estimate(table, np.full(len(table), 0.5), WpaSettings(min_shrinkage_group=999))
    contrasts = [e for e in estimates if e.q is not None]
    assert len(contrasts) == 120  # B and C against A, the most played, for every champion
    assert {e.versus for e in contrasts} == {"A"}
    assert all(e.q is not None and e.q > 0.05 for e in contrasts)
    assert all(Flag.NO_CLEAR_DIFFERENCE in e.flags for e in contrasts)
    assert all(Flag.NO_CLEAR_DIFFERENCE in e.flags for e in estimates)


def test_a_real_difference_is_claimed_against_the_most_played(
    table_factory: TableFactory,
) -> None:
    rng = np.random.default_rng(9)
    options = rng.choice(["A", "B", "C"], size=6000, p=[0.5, 0.3, 0.2])
    win_rate = np.where(options == "C", 0.62, 0.5)
    outcomes = (rng.random(6000) < win_rate).astype(int).tolist()
    estimates = by_option(estimate(table_factory(options.tolist(), outcomes),
                                   np.full(6000, 0.5), WpaSettings()))  # fmt: skip
    assert estimates["A"].q is None  # the reference
    assert estimates["C"].versus == "A"
    assert estimates["C"].q is not None
    assert estimates["C"].q <= 0.05
    assert Flag.NO_CLEAR_DIFFERENCE not in estimates["C"].flags
    assert Flag.NO_CLEAR_DIFFERENCE not in estimates["A"].flags  # something differs from it
    assert Flag.NO_CLEAR_DIFFERENCE in estimates["B"].flags


def test_low_sample_options_are_not_in_the_family(table_factory: TableFactory) -> None:
    rng = np.random.default_rng(10)
    options = ["A"] * 2000 + ["B"] * 1500 + ["C"] * 250
    outcomes = (rng.random(len(options)) < 0.5).astype(int).tolist()
    estimates = by_option(estimate(table_factory(options, outcomes),
                                   np.full(len(options), 0.5), WpaSettings()))  # fmt: skip
    assert Flag.LOW_SAMPLE in estimates["C"].flags
    assert estimates["C"].q is None
    assert Flag.NO_CLEAR_DIFFERENCE not in estimates["C"].flags
    assert estimates["B"].q is not None
