import numpy as np
import pytest

from stronk_synth.generator import SynthConfig, generate


def test_same_seed_same_games() -> None:
    a, b = generate(SynthConfig(games=500)), generate(SynthConfig(games=500))
    assert (a.decisions.option == b.decisions.option).all()
    assert (a.decisions.outcome == b.decisions.outcome).all()


def test_truth_matches_planted_effects() -> None:
    truth = generate(SynthConfig(games=5000)).truth
    assert truth[(1, "A")] == pytest.approx(0.02, abs=1e-3)
    assert truth[(1, "C")] == pytest.approx(-truth[(1, "A")])
    assert truth[(2, "B")] == pytest.approx(0.0)
    assert truth[(3, "E")] == pytest.approx(0.0)


def test_hidden_skill_confounds_only_when_enabled() -> None:
    def a_rate_by_proxy(hidden: float) -> float:
        table = generate(SynthConfig(games=20_000, hidden_skill_choice=hidden)).decisions
        slot1 = table.slot == 1
        proxy = table.features[slot1, 1]
        picked_a = table.option[slot1] == "A"
        return float(picked_a[proxy > 1].mean() - picked_a[proxy < -1].mean())

    assert a_rate_by_proxy(0.6) > a_rate_by_proxy(0.0) + 0.1


def test_one_row_per_game_and_slot() -> None:
    table = generate(SynthConfig(games=300)).decisions
    assert len(table) == 900
    assert sorted(np.unique(table.slot).tolist()) == [1, 2, 3]
