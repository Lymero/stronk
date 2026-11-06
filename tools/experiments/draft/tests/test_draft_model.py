"""The draft model recovers effects planted in synthetic games, and scores partial drafts."""

from __future__ import annotations

import numpy as np
import pytest
from draft_model import (
    BOTTOM,
    UTILITY,
    Draft,
    Floats,
    Games,
    Shares,
    Vocab,
    design,
    enemy_positions,
    expit,
    fit,
    penalties,
    score,
    vocab_of,
)

# Six champions per role: role r's champions are 10r + 0..5.
STRONG = 1  # +0.20 logit in every role
WEAK = 2  # -0.20
COUNTER = (0, 3, 4)  # in TOP, champion 3 beats champion 4 by 0.40
DUO = (31, 41)  # bottom 31 with support 41: +0.30
ONE_TRICK = 5  # played by practised players, but no stronger
LAM = {"main": 10.0, "lane": 10.0, "duo": 10.0, "cross": 10.0, "comp": 10.0}


def synthetic(n: int, seed: int = 1) -> Games:
    rng = np.random.default_rng(seed)
    champion = np.empty((n, 2, 5), dtype=np.int64)
    for r in range(5):
        champion[:, :, r] = 10 * r + rng.integers(0, 6, size=(n, 2))
    practice = rng.exponential(0.5, size=(n, 2, 5))
    practice[champion % 10 == ONE_TRICK] += 2.0
    skill = rng.normal(0, 0.05, size=(n, 2, 5))
    eta = np.zeros(n)
    for t, sign in ((0, 1.0), (1, -1.0)):
        own = champion[:, t] % 10
        eta += sign * (0.2 * (own == STRONG).sum(1) - 0.2 * (own == WEAK).sum(1))
        eta += sign * 0.15 * practice[:, t].sum(1)
        eta += sign * 2.0 * skill[:, t].sum(1)
        eta += (
            sign * 0.3 * ((champion[:, t, BOTTOM] == DUO[0]) & (champion[:, t, UTILITY] == DUO[1]))
        )
    r, a, b = COUNTER
    top = champion[:, :, r] % 10
    eta += 0.4 * ((top[:, 0] == a) & (top[:, 1] == b)) - 0.4 * ((top[:, 0] == b) & (top[:, 1] == a))
    win = (rng.random(n) < expit(eta)).astype(float)
    ids = np.array([f"G{i}" for i in range(n)])
    return Games(ids, champion, skill, practice, win)


type Fitted = tuple[Games, Vocab, Floats]


@pytest.fixture(scope="module")
def fitted() -> Fitted:
    games = synthetic(60_000)
    v = vocab_of(games, magic=())
    coef = fit(design(games, v), games.blue_win, penalties(v, LAM))
    return games, v, coef


def test_planted_champion_effects_are_recovered_and_practice_is_taken_out(fitted: Fitted) -> None:
    _, v, coef = fitted
    for r in range(5):
        main = {c % 10: coef[col] for (role, c), col in v.main.items() if role == r}
        mean = np.mean(list(main.values()))
        assert main[STRONG] - mean == pytest.approx(0.2 - 0.0, abs=0.08)
        assert main[WEAK] - mean == pytest.approx(-0.2, abs=0.08)
        # One-tricks win more from practice alone: their champion is no stronger.
        assert main[ONE_TRICK] - mean == pytest.approx(0.0, abs=0.08)
    assert coef[2] == pytest.approx(0.15, abs=0.03)


def test_a_planted_counter_and_duo_are_recovered(fitted: Fitted) -> None:
    _, v, coef = fitted
    r, a, b = COUNTER
    assert coef[v.lane[(r, a, b)]] == pytest.approx(0.4, abs=0.15)
    assert coef[v.duo[DUO]] == pytest.approx(0.3, abs=0.15)


def test_a_blind_pick_ranks_the_strong_champion_first(fitted: Fitted) -> None:
    games, v, coef = fitted
    shares = Shares.of(games, frozenset())
    ranked = score(Draft(role=1), v, shares, coef)
    assert ranked[0].champion == 10 + STRONG
    assert ranked[-1].champion == 10 + WEAK
    # Against the average pick: the effects of the role sum to about 0 weighted by picks.
    assert sum(s.effect * s.share for s in ranked) == pytest.approx(0.0, abs=0.2)


def test_a_known_enemy_laner_brings_its_counter_up(fitted: Fitted) -> None:
    games, v, coef = fitted
    shares = Shares.of(games, frozenset())
    r, a, b = COUNTER
    blind = {s.champion: s.effect for s in score(Draft(role=r), v, shares, coef)}
    against = {
        s.champion: s.effect for s in score(Draft(role=r, enemy_roles={r: b}), v, shares, coef)
    }
    assert against[a] - blind[a] > 5  # about +10 wins per 100 against b, +2 blind
    # An enemy pick without a role counts by how often it plays the role: 4 is always TOP.
    unknown = {s.champion: s.effect for s in score(Draft(role=r, enemies=[b]), v, shares, coef)}
    assert unknown[a] == pytest.approx(against[a], abs=0.5)


def test_the_bottom_partner_is_counted_when_known(fitted: Fitted) -> None:
    games, v, coef = fitted
    shares = Shares.of(games, frozenset())
    alone = {s.champion: s.effect for s in score(Draft(role=BOTTOM), v, shares, coef)}
    paired = {
        s.champion: s.effect
        for s in score(Draft(role=BOTTOM, allies={UTILITY: DUO[1]}), v, shares, coef)
    }
    assert paired[DUO[0]] - alone[DUO[0]] > 3


def test_enemy_roles_follow_how_each_champion_plays_and_the_open_roles() -> None:
    role = {7: np.array([0.9, 0.1, 0, 0, 0]), 8: np.array([0.6, 0.4, 0, 0, 0])}
    shares = Shares([{} for _ in range(5)], role, np.zeros(5))
    p = enemy_positions(Draft(role=2, enemies=[7, 8]), shares)
    assert p.sum(axis=1) == pytest.approx([1.0, 1.0])
    assert p[0, 0] > 0.8  # 7 takes top,
    assert p[1, 1] > 0.8  # so 8 is the jungler
    # With top known, 8 can only jungle.
    p = enemy_positions(Draft(role=2, enemies=[8], enemy_roles={0: 7}), shares)
    assert p[0, 1] == pytest.approx(1.0, abs=1e-4)
