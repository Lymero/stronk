"""Multiple-comparison control: Benjamini-Hochberg false discovery rate (ADR-036).

A run estimates thousands of options; at 95% each, dozens of intervals exclude zero by chance
alone. An estimate is only called clear when it survives BH across every estimate of the run.
"""

from __future__ import annotations

import math

import numpy as np

from stronk_pipeline.domain.logistic import Floats


def two_sided_p(estimate: float, std_error: float) -> float:
    """P(|Z| >= |estimate / std_error|) under a normal approximation; 1 without a usable error.

    The bootstrap gives the standard error, not the p-value itself: 200 resamples can't
    resolve p below 1/200, and BH over thousands of estimates needs thresholds near 1e-5.
    """
    if not (math.isfinite(estimate) and math.isfinite(std_error)) or std_error <= 0.0:
        return 1.0
    return math.erfc(abs(estimate / std_error) / math.sqrt(2.0))


def benjamini_hochberg(p: Floats) -> Floats:
    """Adjusted p-values (q-values): reject every hypothesis with q <= the target rate."""
    m = len(p)
    if m == 0:
        return np.zeros(0)
    order = np.argsort(p, kind="stable")
    scaled = p[order] * m / np.arange(1, m + 1)
    # Each q is the smallest scaled value at or above its rank, so q never decreases with p.
    adjusted = np.minimum(np.minimum.accumulate(scaled[::-1])[::-1], 1.0)
    q = np.empty(m)
    q[order] = adjusted
    return q
