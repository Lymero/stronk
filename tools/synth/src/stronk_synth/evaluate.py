"""Synthetic-truth metrics: how well WPA v1 recovers planted effects, over several seeds.

Every seed includes a many-option slot with a rare tail (slot 4). Two scenarios: `clean` (no
hidden confounder on the choice) and `confounded` (hidden skill
drives both the choice of A and winning). Metrics feed `metrics/floors.toml`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.winprob import BaselineWinProb
from stronk_pipeline.domain.wpa.overlap_weighted import OverlapWeightedEstimator
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate, WpaSettings
from stronk_synth.generator import TAIL, SynthConfig, generate

SEEDS = tuple(range(101, 109))
SCENARIOS = {
    "clean": SynthConfig(hidden_skill_choice=0.0),
    "confounded": SynthConfig(),
}


ESTIMATORS = {"": ReferenceEstimatorV1(), "overlap_weighted.": OverlapWeightedEstimator()}
"""Metric prefix -> estimator. The default (`wpa.estimate`) has no prefix; floors check it."""


def evaluate(seeds: tuple[int, ...] = SEEDS) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for prefix, estimator in ESTIMATORS.items():
        for name, base in SCENARIOS.items():
            scenario = _scenario(base, seeds, estimator.estimate)
            metrics |= {f"synthetic.{prefix}{name}.{k}": v for k, v in scenario.items()}
    return metrics


def _scenario(
    base: SynthConfig,
    seeds: tuple[int, ...],
    estimate: Callable[[DecisionTable, Floats, WpaSettings], list[OptionEstimate]],
) -> dict[str, float]:
    errors: list[float] = []
    covered: list[bool] = []
    planted_bias: list[float] = []
    meta_lock_flagged: list[bool] = []
    planted_clear: list[bool] = []
    common_estimated: list[bool] = []
    tail_flagged: list[bool] = []
    g_share_kept: list[float] = []
    for seed in seeds:
        games = generate(replace(base, seed=seed))
        table = games.decisions
        wp = BaselineWinProb.fit(table).predict(table)
        for e in estimate(table, wp, WpaSettings(seed=seed)):
            truth = games.truth[(e.slot, e.option)]
            if e.slot == 3:
                meta_lock_flagged.append(Flag.LOW_OVERLAP in e.flags and e.wpa is None)
            if e.option in TAIL:
                tail_flagged.append(Flag.LOW_OVERLAP in e.flags and e.wpa is None)
            elif e.slot == 4:
                common_estimated.append(e.wpa is not None)
            if e.option in ("A", "G"):
                planted_clear.append(Flag.NO_CLEAR_DIFFERENCE not in e.flags)
            if e.option == "G" and e.wpa is not None:
                g_share_kept.append(e.wpa / truth)
            # Slot 4 checks overlap and G's share kept, not accuracy: v1 attenuates
            # effects of situational choices (ADR-036), so it doesn't target that truth.
            if e.wpa is None or e.ci is None or e.slot == 4:
                continue
            errors.append(abs(e.wpa - truth))
            covered.append(e.ci[0] <= truth <= e.ci[1])
            if e.option == "A":
                planted_bias.append(e.wpa - truth)
    return {
        "mean_abs_error": float(np.mean(errors)),
        "max_abs_error": float(np.max(errors)),
        "coverage": float(np.mean(covered)),
        "planted_bias": float(np.mean(planted_bias)),
        "meta_lock_flagged": float(np.mean(meta_lock_flagged)),
        "planted_clear": float(np.mean(planted_clear)),
        "common_options_estimated": float(np.mean(common_estimated)),
        "long_tail_flagged": float(np.mean(tail_flagged)),
        "g_share_kept": float(np.mean(g_share_kept)),
    }
