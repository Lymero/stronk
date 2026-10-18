"""Synthetic per-minute frames with a known win probability, for winprob tests."""

import numpy as np

from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats, expit
from stronk_pipeline.domain.winprob import WP_FEATURES

GOLD = WP_FEATURES.index("gold_diff")


def truth(gold: Floats, minute: Floats) -> Floats:
    """P(win) for a team `gold` thousand ahead at `minute`: leads matter more later."""
    return expit(0.04 * gold * minute)


def frames(matches: int, minutes: int = 25, seed: int = 0) -> FrameTable:
    """Gold lead is a random walk; the final lead decides the winner through `truth`. Every
    minute appears from both sides, leads negated, as extract writes it."""
    rng = np.random.default_rng(seed)
    ids: list[str] = []
    teams: list[int] = []
    mins: list[float] = []
    outcomes: list[int] = []
    rows: list[Floats] = []
    for g in range(matches):
        lead = np.cumsum(rng.normal(0.0, 0.6, size=minutes))
        blue_wins = rng.random() < truth(lead[-1:], np.array([float(minutes)]))[0]
        for minute in range(minutes):
            for team, sign in ((100, 1.0), (200, -1.0)):
                x = np.zeros(len(WP_FEATURES))
                x[GOLD] = sign * lead[minute]
                ids.append(f"EUW1_{g}")
                teams.append(team)
                mins.append(float(minute))
                outcomes.append(int(blue_wins == (team == 100)))
                rows.append(x)
    return FrameTable(
        match_id=np.array(ids),
        team=np.array(teams, dtype=np.int64),
        minute=np.array(mins),
        outcome=np.array(outcomes, dtype=np.int64),
        features=np.array(rows),
        feature_names=WP_FEATURES,
    )
