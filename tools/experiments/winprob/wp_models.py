"""Win probability models compared with production's logistic one (ADR-084).

Each is a `WinProbModel` (feature_names, predict), fitted on the training matches of a frame
table as `winprob.train` fits production's, so `fit_compare.py` and `wpa_compare.py` treat them
alike. Not part of the pipeline: an experiment kept so it can be rerun on more data.

- `logistic`: production's form, leads, minute and lead x minute.
- `gam-minute`: the minute as a restricted cubic spline, every lead varying with it.
- `gam-curves`: also gold, XP and kill leads curved (splines, symmetric around 0).
- `gam-odd-pairs`: also gold with each other lead, odd in the leads. Even terms (a plain
  product of two leads) are cancelled by the symmetric prediction (ADR-030) and add nothing.
- `lightgbm`: production's other candidate's family, plain trees, every lead monotone.
- `lightgbm-linear`: trees with a linear model in each leaf, every lead monotone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
from numpy.typing import NDArray

from stronk_pipeline.domain.logistic import Floats, LogisticModel, fit_logistic_chunks
from stronk_pipeline.domain.winprob import TRAIN, VALID, WP_FEATURES, match_parts
from stronk_pipeline.ports import WinProbModel

FEATURES = tuple(WP_FEATURES)
CHUNK = 400_000
"""Rows designed at once: the spline designs are about 80 columns wide."""
CURVED = ("gold_diff", "xp_diff", "kill_diff")

type Design = Callable[[Floats, Floats], Floats]
"""(leads in FEATURES order, minute) -> the logistic model's inputs."""
type Indices = NDArray[np.intp]


@dataclass(frozen=True)
class Frames:
    """A frame table in memory: leads in FEATURES order, minute, outcome, each row's match (an
    index) and part of the split (`match_parts`)."""

    x: Floats
    minute: Floats
    outcome: Floats
    match: NDArray[np.intp]
    part: NDArray[np.int64]

    def rows(self, part: int) -> Indices:
        return np.flatnonzero(self.part == part)


def read_frames(path: Path) -> Frames:
    cols = [f"f_{f}" for f in FEATURES]
    df = pl.read_parquet(path, columns=["match_id", "minute", "outcome", *cols])
    ids: list[str] = df["match_id"].cast(pl.String).to_list()
    parts = match_parts(ids)
    _, match = np.unique(np.asarray(ids), return_inverse=True)
    return Frames(
        x=df.select(cols).to_numpy().astype(np.float64),
        minute=df["minute"].to_numpy().astype(np.float64),
        outcome=df["outcome"].to_numpy().astype(np.float64),
        match=match.astype(np.intp),
        part=np.array([parts[m] for m in ids], dtype=np.int64),
    )


def rcs(x: Floats, knots: Floats) -> Floats:
    """Restricted cubic spline basis: x, then len(knots) - 2 curves, linear beyond the outer
    knots (Harrell's form, scaled by the outer knots' spread squared)."""
    t = knots
    k = len(t)

    def cube(v: Floats) -> Floats:
        return np.maximum(v, 0.0) ** 3

    span = t[k - 1] - t[k - 2]
    cols = [x]
    for j in range(k - 2):
        c = (
            cube(x - t[j])
            - cube(x - t[k - 2]) * (t[k - 1] - t[j]) / span
            + cube(x - t[k - 1]) * (t[k - 2] - t[j]) / span
        )
        cols.append(c / (t[-1] - t[0]) ** 2)
    return np.column_stack(cols)


def designs(frames: Frames) -> dict[str, Design]:
    """Each logistic form's inputs, knots placed on the training matches."""
    train = frames.rows(TRAIN)
    minute_knots = np.quantile(frames.minute[train], [0.05, 0.275, 0.5, 0.725, 0.95])
    curved = {FEATURES.index(n): n for n in CURVED}
    lead_knots: dict[int, Floats] = {}
    for j in curved:
        q = np.quantile(np.abs(frames.x[train, j]), [0.5, 0.9])
        lead_knots[j] = np.array([-q[1], -q[0], 0.0, q[0], q[1]])
    gold = FEATURES.index("gold_diff")
    others = [j for j in range(len(FEATURES)) if j != gold]

    def logistic(x: Floats, m: Floats) -> Floats:
        return np.hstack([x, m[:, None], x * m[:, None]])

    def minute(x: Floats, m: Floats) -> list[Floats]:
        mb = rcs(m, minute_knots)
        return [x, mb] + [x * mb[:, [c]] for c in range(mb.shape[1])]

    def curves(x: Floats, m: Floats) -> list[Floats]:
        blocks = minute(x, m)
        for j, knots in lead_knots.items():
            bent = rcs(x[:, j], knots)[:, 1:]
            blocks += [bent, bent * m[:, None]]
        return blocks

    def odd_pairs(x: Floats, m: Floats) -> Floats:
        g = x[:, [gold]]
        rest = x[:, others]
        return np.hstack([*curves(x, m), g * np.abs(rest), rest * np.abs(g)])

    return {
        "logistic": logistic,
        "gam-minute": lambda x, m: np.hstack(minute(x, m)),
        "gam-curves": lambda x, m: np.hstack(curves(x, m)),
        "gam-odd-pairs": odd_pairs,
    }


@dataclass(frozen=True)
class DesignedLogistic:
    """A `WinProbModel`: logistic regression on a design of the leads and minute."""

    design: Design
    model: LogisticModel
    feature_names: tuple[str, ...] = FEATURES

    def predict(self, features: Floats, minute: Floats) -> Floats:
        out = np.empty(len(features))
        for s in range(0, len(features), CHUNK):
            rows = slice(s, s + CHUNK)
            out[rows] = self.model.predict(self.design(features[rows], minute[rows]))
        return out


@dataclass(frozen=True)
class Boosted:
    """A `WinProbModel` on a LightGBM booster over (leads, minute)."""

    booster: lgb.Booster
    feature_names: tuple[str, ...] = FEATURES

    def predict(self, features: Floats, minute: Floats) -> Floats:
        raw = self.booster.predict(np.column_stack([features, minute]))  # pyright: ignore[reportUnknownMemberType]
        return np.asarray(raw, dtype=np.float64).reshape(len(features))


def fit_designed(frames: Frames, design: Design) -> DesignedLogistic:
    train = frames.rows(TRAIN)

    def chunks() -> Iterator[tuple[Floats, Floats]]:
        for s in range(0, len(train), CHUNK):
            r = train[s : s + CHUNK]
            yield design(frames.x[r], frames.minute[r]), frames.outcome[r]

    return DesignedLogistic(design, fit_logistic_chunks(chunks))


def fit_lightgbm(frames: Frames, leaves: int, min_leaf: int, linear: bool, seed: int) -> Boosted:
    """Early stopping on the validation matches; all cores, so not byte-reproducible across
    machines as production's is."""
    params: dict[str, object] = {
        "objective": "binary",
        "learning_rate": 0.05,
        "num_leaves": leaves,
        "min_data_in_leaf": min_leaf,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": seed,
        "monotone_constraints": [1] * len(FEATURES) + [0],
        "linear_tree": linear,
    }
    if linear:
        params["linear_lambda"] = 1.0

    def inputs(rows: Indices) -> Floats:
        return np.column_stack([frames.x[rows], frames.minute[rows]])

    train, valid = frames.rows(TRAIN), frames.rows(VALID)
    train_set = lgb.Dataset(inputs(train), label=frames.outcome[train], params=params)
    valid_set = lgb.Dataset(inputs(valid), label=frames.outcome[valid], reference=train_set)
    booster = lgb.train(  # pyright: ignore[reportUnknownMemberType]
        params,
        train_set,
        num_boost_round=4000,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    booster.free_dataset()
    return Boosted(booster)


def fitters(frames: Frames) -> dict[str, Callable[[], WinProbModel]]:
    """Every model by name, fitted when called. Of the 12 LightGBM settings tried on Emerald+
    16.21 (15, 63 or 255 leaves; 200 or 2,000 rows per leaf; plain or linear) the best of each
    kind is kept; the linear one under three seeds, for the noise a model change must beat."""
    out: dict[str, Callable[[], WinProbModel]] = {
        name: (lambda d=design: fit_designed(frames, d)) for name, design in designs(frames).items()
    }
    out["lightgbm"] = lambda: fit_lightgbm(frames, 63, 2000, linear=False, seed=0)
    for seed in (0, 1, 2):
        out[f"lightgbm-linear-s{seed}"] = lambda s=seed: fit_lightgbm(
            frames, 63, 2000, linear=True, seed=s
        )
    return out
