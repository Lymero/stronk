"""Patch backtest, stability half: do one patch's head-to-head contrasts point the same way on
the next? (The other half, items Riot changed moving the right way, needs the patch changes.)

A contrast is an option against its point's most played option (ADR-036), keyed by champion,
role, slot, option and `versus`; a contrast only counts when both patches measured it with the
same `versus`. Signs are compared on `contrast`, the effect `q` tests (ADR-055).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from stronk_pipeline.domain.wpa.types import OptionEstimate

type ContrastKey = tuple[str, str, int, str, str]


@dataclass(frozen=True)
class Claim:
    """A contrast clear on the earlier patch (q at most the FDR), and how it did on the later."""

    key: ContrastKey
    earlier: float
    earlier_q: float
    later: float | None
    """None when the later patch didn't measure it."""
    later_q: float | None


@dataclass(frozen=True)
class Backtest:
    earlier_contrasts: int
    later_contrasts: int
    paired: int
    """Contrasts measured on both patches."""
    sign_agreement: float | None
    """Paired contrasts with the same sign on both (0.5 is a coin flip); None with none paired."""
    clear: int
    """Paired contrasts whose earlier interval excludes zero."""
    clear_sign_agreement: float | None
    correlation: float | None
    slope: float | None
    """Least-squares slope of later on earlier: how much of an earlier effect carries over."""
    claims: tuple[Claim, ...]
    claims_held: int
    """Claims measured again with the same sign."""
    claims_replicated: int
    """Claims clear again on the later patch, with the same sign."""


def contrasts(estimates: Sequence[OptionEstimate]) -> dict[ContrastKey, OptionEstimate]:
    return {
        (e.champion, e.role, e.slot, e.option, e.versus): e
        for e in estimates
        if e.versus is not None and e.q is not None and e.contrast is not None
    }


def backtest(
    earlier: Sequence[OptionEstimate], later: Sequence[OptionEstimate], fdr: float
) -> Backtest:
    old, new = contrasts(earlier), contrasts(later)
    paired = sorted(old.keys() & new.keys())
    a = np.array([_effect(old[k]) for k in paired], dtype=np.float64)
    b = np.array([_effect(new[k]) for k in paired], dtype=np.float64)
    same = np.sign(a) * np.sign(b) > 0
    clear = np.array([_excludes_zero(old[k].contrast_ci) for k in paired], dtype=np.bool_)
    claims = tuple(
        Claim(
            key=k,
            earlier=_effect(e),
            earlier_q=_q(e),
            later=_effect(new[k]) if k in new else None,
            later_q=_q(new[k]) if k in new else None,
        )
        for k, e in sorted(old.items())
        if _q(e) <= fdr
    )
    held = [c for c in claims if c.later is not None and c.earlier * c.later > 0]
    varies = len(paired) > 2 and float(np.std(a)) > 0 and float(np.std(b)) > 0
    return Backtest(
        earlier_contrasts=len(old),
        later_contrasts=len(new),
        paired=len(paired),
        sign_agreement=float(np.mean(same)) if paired else None,
        clear=int(clear.sum()),
        clear_sign_agreement=float(np.mean(same[clear])) if clear.any() else None,
        correlation=float(np.corrcoef(a, b)[0, 1]) if varies else None,
        slope=float(np.polyfit(a, b, 1)[0]) if varies else None,
        claims=claims,
        claims_held=len(held),
        claims_replicated=sum(1 for c in held if c.later_q is not None and c.later_q <= fdr),
    )


def _effect(e: OptionEstimate) -> float:
    return 0.0 if e.contrast is None else e.contrast


def _q(e: OptionEstimate) -> float:
    return 1.0 if e.q is None else e.q


def _excludes_zero(ci: tuple[float, float] | None) -> bool:
    return ci is not None and (ci[0] > 0 or ci[1] < 0)
