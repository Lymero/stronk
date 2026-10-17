"""Required synthetic-truth test (docs/wpa-method.md, section 8.1).

Item A truly adds +2% and is picked more by (hidden) skilled players; item B adds nothing but is
bought mostly when ahead; E is a 97% pick. WPA v1 must recover A, give B about 0, and refuse to
put a number on the meta-locked choice.
"""

import numpy as np
import pytest

from stronk_pipeline.domain.winprob import BaselineWinProb
from stronk_pipeline.domain.wpa.reference import estimate
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate
from stronk_synth.generator import SynthConfig, SynthGames, generate


@pytest.fixture(scope="module")
def games() -> SynthGames:
    return generate(SynthConfig())


@pytest.fixture(scope="module")
def estimates(games: SynthGames) -> dict[str, OptionEstimate]:
    table = games.decisions
    wp = BaselineWinProb.fit(table).predict(table)
    return {e.option: e for e in estimate(table, wp)}


def raw_win_rate_gap(games: SynthGames, option: str, slot: int) -> float:
    table = games.decisions
    at_slot = table.slot == slot
    chosen = at_slot & (table.option == option)
    return float(table.outcome[chosen].mean() - table.outcome[at_slot & ~chosen].mean())


def test_planted_effect_is_recovered(estimates: dict[str, OptionEstimate]) -> None:
    a = estimates["A"]
    assert a.ci is not None
    assert a.ci[0] <= 0.02 <= a.ci[1]
    assert a.ci[0] > 0.0


def test_item_bought_while_ahead_gets_no_credit(
    games: SynthGames, estimates: dict[str, OptionEstimate]
) -> None:
    assert raw_win_rate_gap(games, "B", slot=2) > 0.1  # the bias is real...
    b = estimates["B"]
    assert b.wpa is not None
    assert b.ci is not None
    assert abs(b.wpa) < 0.01  # ...and removed
    assert b.ci[0] <= 0.0 <= b.ci[1]


def test_meta_locked_choice_gets_low_overlap(
    games: SynthGames, estimates: dict[str, OptionEstimate]
) -> None:
    picks = games.decisions.option[games.decisions.slot == 3]
    pick_rate = np.count_nonzero(picks == "E") / len(picks)
    assert 0.95 < pick_rate < 0.99
    for option in ("E", "F"):
        assert Flag.LOW_OVERLAP in estimates[option].flags
        assert estimates[option].wpa is None
