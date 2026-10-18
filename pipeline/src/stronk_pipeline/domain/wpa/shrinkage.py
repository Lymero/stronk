"""Empirical Bayes shrinkage toward a group mean (DerSimonian-Laird random effects)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Shrunk:
    estimates: NDArray[np.float64]
    weights: NDArray[np.float64]
    """Weight on each raw estimate; 1 means no shrinkage."""
    prior: float
    std_errors: NDArray[np.float64]
    """Of each shrunk estimate: sqrt(w se^2 + (1 - w)^2 Var(prior)). The prior is itself
    estimated from the group, so a fully shrunk estimate keeps the prior's uncertainty."""


def shrink(estimates: NDArray[np.float64], std_errors: NDArray[np.float64]) -> Shrunk:
    """Pull each estimate toward the precision-weighted mean by its share of total variance.

    w_i = tau^2 / (tau^2 + se_i^2), with tau^2 the between-estimate variance (method of moments).
    """
    variances = np.maximum(std_errors**2, 1e-12)
    fixed_weights = 1.0 / variances
    mean = float(np.sum(fixed_weights * estimates) / np.sum(fixed_weights))
    q = float(np.sum(fixed_weights * (estimates - mean) ** 2))
    denom = float(np.sum(fixed_weights) - np.sum(fixed_weights**2) / np.sum(fixed_weights))
    tau2 = max(0.0, (q - (len(estimates) - 1)) / denom) if denom > 0 else 0.0
    random_weights = 1.0 / (variances + tau2)
    prior = float(np.sum(random_weights * estimates) / np.sum(random_weights))
    weights = tau2 / (tau2 + variances)
    prior_variance = 1.0 / float(np.sum(random_weights))
    shrunk_variances = weights * variances + (1.0 - weights) ** 2 * prior_variance
    return Shrunk(
        weights * estimates + (1.0 - weights) * prior, weights, prior, np.sqrt(shrunk_variances)
    )
