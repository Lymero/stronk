"""Baseline win probability model: logistic regression on situation features.

A stand-in until the `winprob` stage (M2) trains the LightGBM model on per-minute frames.
It is fitted on the decisions themselves, without the chosen option, so it estimates
P(win | situation at decision time).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats, LogisticModel, fit_logistic


@dataclass(frozen=True)
class BaselineWinProb:
    model: LogisticModel

    @classmethod
    def fit(cls, table: DecisionTable) -> BaselineWinProb:
        return cls(fit_logistic(_inputs(table), table.outcome.astype(np.float64)))

    def predict(self, table: DecisionTable) -> Floats:
        return self.model.predict(_inputs(table))


def _inputs(table: DecisionTable) -> Floats:
    """Features, minute, and their interaction: the same lead matters more later on."""
    minute = table.minute[:, None]
    return np.hstack([table.features, minute, table.features * minute])
