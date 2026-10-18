"""Windowed outcome: the team's WP some minutes after a decision (ADR-039)."""

import numpy as np
import pytest

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.wpa.outcome import team_of, windowed_outcome


def frames(rows: list[tuple[str, int, float, float]]) -> tuple[FrameTable, np.ndarray]:
    """(match, team, minute, wp) rows, in any order."""
    table = FrameTable(
        match_id=np.array([r[0] for r in rows]),
        team=np.array([r[1] for r in rows], dtype=np.int64),
        minute=np.array([r[2] for r in rows]),
        outcome=np.zeros(len(rows), dtype=np.int64),
        features=np.zeros((len(rows), 1)),
        feature_names=("gold_diff",),
    )
    return table, np.array([r[3] for r in rows])


def decisions(rows: list[tuple[str, int, float, int]]) -> DecisionTable:
    """(match, participant, minute, outcome) rows."""
    n = len(rows)
    return DecisionTable.create(
        match_id=np.array([r[0] for r in rows]),
        participant=np.array([r[1] for r in rows], dtype=np.int64),
        champion=np.full(n, "Ahri"),
        champion_class=np.full(n, "mage"),
        role=np.full(n, "MIDDLE"),
        slot=np.arange(1, n + 1, dtype=np.int64),
        minute=np.array([r[2] for r in rows]),
        option=np.full(n, "A"),
        outcome=np.array([r[3] for r in rows], dtype=np.int64),
        features=np.zeros((n, 1)),
        feature_names=("gold_diff",),
    )


def test_takes_the_teams_wp_at_the_first_frame_after_the_window() -> None:
    f, wp = frames([("M1", 200, 15.0, 0.30), ("M1", 100, 15.0, 0.70), ("M1", 100, 14.0, 0.60),
                    ("M1", 200, 14.0, 0.40)])  # fmt: skip
    d = decisions([("M1", 2, 8.4, 1), ("M1", 7, 8.4, 0)])
    out = windowed_outcome(d, f, wp, 6.0)  # 14.4 -> the frame at minute 15
    assert out[d.participant == 2] == pytest.approx([0.70])
    assert out[d.participant == 7] == pytest.approx([0.30])


def test_falls_back_to_the_result_when_the_game_ends_first() -> None:
    f, wp = frames([("M1", 100, 20.0, 0.9)])
    d = decisions([("M1", 3, 18.0, 1), ("M2", 3, 5.0, 0)])  # M2 has no frames at all
    assert windowed_outcome(d, f, wp, 5.0).tolist() == [1.0, 0.0]


def test_team_follows_riot_participant_ids() -> None:
    assert team_of(np.arange(1, 11)).tolist() == [100] * 5 + [200] * 5


def test_rejects_a_non_positive_window() -> None:
    f, wp = frames([("M1", 100, 1.0, 0.5)])
    with pytest.raises(ValueError, match="positive"):
        windowed_outcome(decisions([("M1", 1, 0.0, 1)]), f, wp, 0.0)
