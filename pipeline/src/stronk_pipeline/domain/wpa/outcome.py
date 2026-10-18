"""What an event score measures against WP at the decision (docs/wpa-method.md, section 5).

The final result is unbiased but noisy: a game has many later decisions. The windowed outcome
is the decision maker's team's WP Δ minutes later, or the result when the game ends first; it
measures a shorter-term effect with less noise.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats


def team_of(participant: NDArray[np.int64]) -> NDArray[np.int64]:
    """Participants 1 to 5 play for team 100 (`Match` rejects games where they don't)."""
    return np.where(participant <= 5, 100, 200)


def windowed_outcome(
    decisions: DecisionTable, frames: FrameTable, frame_wp: Floats, minutes: float
) -> Floats:
    """WP of the decision maker's team at the first frame at least `minutes` after each
    decision; the final result when the game has no such frame. `frame_wp` is WP for each row
    of `frames`, seen from that row's team."""
    if minutes <= 0:
        raise ValueError("the window must be positive")
    if frame_wp.shape != (len(frames),):
        raise ValueError(f"frame_wp has shape {frame_wp.shape}, expected ({len(frames)},)")
    team = team_of(decisions.participant)
    out = decisions.outcome.astype(np.float64)
    order = np.lexsort((frames.minute, frames.team, frames.match_id))
    keys = np.char.add(np.char.add(frames.match_id[order], ":"), frames.team[order].astype(str))
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    ends = np.r_[starts[1:], len(keys)]
    groups: dict[str, tuple[int, int]] = {
        str(keys[s]): (int(s), int(e)) for s, e in zip(starts.tolist(), ends.tolist(), strict=True)
    }
    wanted = np.char.add(np.char.add(decisions.match_id, ":"), team.astype(str))
    minute, wp = frames.minute[order], frame_wp[order]
    targets = decisions.minute + minutes
    for i in range(len(wanted)):
        group = groups.get(str(wanted[i]))
        if group is None:
            continue  # no frames for this game: keep the result
        s, e = group
        later: NDArray[np.intp] = np.searchsorted(minute[s:e], targets[i : i + 1])
        j = s + int(later[0])
        if j < e:
            out[i] = wp[j]
    return out
