"""WPA v1 with overlap weights (Li, Morgan & Zaslavsky 2018; ADR-037).

Same decision points, overlap gate, bootstrap, shrinkage and claims as the reference; only the
effect differs. Choosers of option A are weighted by 1 - e and the others by e, with e = P(A)
in the situation. Weighted this way both groups have the same distribution of situations, so
the effect is E[e(1-e) D(x)] / E[e(1-e)]: A against the alternatives chosen in the same
situation, averaged where both are realistically chosen. The difference of plain means (v1)
also carries e, which shrinks effects of choices the situation predicts toward zero.

Scores are outcome - WP(x); WP cancels from the comparison in expectation whatever its form,
because both groups are weighted to the same situations.
"""

from __future__ import annotations

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.wpa.reference import Bools, Weights, estimate, weighted_means
from stronk_pipeline.domain.wpa.types import OptionEstimate, WpaSettings


def overlap_weighted(
    scores: Floats, mine: Bools, propensity: Floats, weights: Weights
) -> tuple[float, Floats]:
    h = np.where(mine, 1.0 - propensity, propensity)
    point = float(
        np.sum(h[mine] * scores[mine]) / np.sum(h[mine])
        - np.sum(h[~mine] * scores[~mine]) / np.sum(h[~mine])
    )
    boot = weighted_means(weights[:, mine] * h[mine], scores[mine]) - weighted_means(
        weights[:, ~mine] * h[~mine], scores[~mine]
    )
    return point, boot


class OverlapWeightedEstimator:
    id = "overlap-weighted"

    def estimate(
        self, table: DecisionTable, wp: Floats, settings: WpaSettings
    ) -> list[OptionEstimate]:
        return estimate(table, wp, settings, overlap_weighted)
