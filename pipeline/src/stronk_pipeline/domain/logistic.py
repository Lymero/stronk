"""Ridge-stabilised logistic regression by Newton's method: small, plain, deterministic."""

from __future__ import annotations

from collections.abc import Callable, Iterable
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


type Chunks = Callable[[], Iterable[tuple[Floats, Floats]]]
"""(x, y) a chunk of rows at a time; called once for each pass over the rows."""


def fit_logistic_chunks(
    chunks: Chunks, *, ridge: float = 1e-3, max_iter: int = 100, tol: float = 1e-10
) -> LogisticModel:
    """`fit_logistic` on rows read a chunk at a time, for more rows than fit in memory
    (ADR-081): the same standardisation and Newton steps, their sums added chunk by chunk. On
    one chunk the arithmetic is `fit_logistic`'s, operation for operation; on several, the sums
    are added in another order, equal up to rounding."""
    total: Floats | None = None
    n = 0
    for x, _ in chunks():
        part = np.sum(x, axis=0)
        total = part if total is None else total + part
        n += len(x)
    if total is None or n == 0:
        raise ValueError("no rows to fit")
    mean = total / n
    squares: Floats | None = None
    for x, _ in chunks():
        d = x - mean
        part = np.sum(d * d, axis=0)
        squares = part if squares is None else squares + part
    scale = np.sqrt(squares / n) if squares is not None else np.ones(len(mean))
    scale = np.where(scale > 1e-12, scale, 1.0)
    penalty = np.full(len(mean) + 1, ridge)
    penalty[0] = 1e-12
    coef = np.zeros(len(mean) + 1)
    for _ in range(max_iter):
        gradient: Floats | None = None
        hessian: Floats | None = None
        for x, y in chunks():
            z = _design(x, mean, scale)
            p = expit(z @ coef)
            g, h = z.T @ (y - p), (z.T * (p * (1.0 - p))) @ z
            gradient = g if gradient is None else gradient + g
            hessian = h if hessian is None else hessian + h
        if gradient is None or hessian is None:
            raise ValueError("no rows to fit")
        step = np.linalg.solve(hessian + np.diag(penalty), gradient - penalty * coef)
        coef = coef + step
        if np.max(np.abs(step)) < tol:
            break
    return LogisticModel(mean, scale, coef)


def _design(x: Floats, mean: Floats, scale: Floats) -> Floats:
    return np.column_stack([np.ones(len(x)), (x - mean) / scale])
