"""Ridge-stabilised logistic regression by Newton's method: small, plain, deterministic."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

type Floats = NDArray[np.float64]


def expit(eta: Floats) -> Floats:
    return 1.0 / (1.0 + np.exp(-np.clip(eta, -35.0, 35.0)))


@dataclass(frozen=True)
class LogisticModel:
    mean: Floats
    scale: Floats
    coef: Floats
    """Intercept first, then one coefficient per standardised feature."""

    def predict(self, x: Floats) -> Floats:
        return expit(_design(x, self.mean, self.scale) @ self.coef)


def fit_logistic(
    x: Floats, y: Floats, *, ridge: float = 1e-3, max_iter: int = 100, tol: float = 1e-10
) -> LogisticModel:
    """Fit P(y = 1 | x). `ridge` keeps the fit finite under separation; the intercept is free."""
    mean = x.mean(axis=0) if len(x) else np.zeros(x.shape[1])
    scale = x.std(axis=0) if len(x) else np.ones(x.shape[1])
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = _design(x, mean, scale)
    penalty = np.full(z.shape[1], ridge)
    penalty[0] = 1e-12
    coef = np.zeros(z.shape[1])
    for _ in range(max_iter):
        p = expit(z @ coef)
        gradient = z.T @ (y - p) - penalty * coef
        hessian = (z.T * (p * (1.0 - p))) @ z + np.diag(penalty)
        step = np.linalg.solve(hessian, gradient)
        coef = coef + step
        if np.max(np.abs(step)) < tol:
            break
    return LogisticModel(mean, scale, coef)


def _design(x: Floats, mean: Floats, scale: Floats) -> Floats:
    return np.column_stack([np.ones(len(x)), (x - mean) / scale])
