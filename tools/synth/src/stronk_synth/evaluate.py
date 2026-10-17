"""Synthetic-truth metrics: how well WPA v1 recovers planted effects, over several seeds.

Two scenarios: `clean` (no hidden confounder on the choice) and `confounded` (hidden skill
drives both the choice of A and winning). Metrics feed `metrics/floors.toml`.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from stronk_pipeline.domain.winprob import BaselineWinProb
from stronk_pipeline.domain.wpa.reference import estimate
from stronk_pipeline.domain.wpa.types import Flag, WpaSettings
from stronk_synth.generator import SynthConfig, generate

SEEDS = tuple(range(101, 109))
SCENARIOS = {
    "clean": SynthConfig(hidden_skill_choice=0.0),
    "confounded": SynthConfig(),
}


def evaluate(seeds: tuple[int, ...] = SEEDS) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for name, base in SCENARIOS.items():
        errors: list[float] = []
        covered: list[bool] = []
        planted_bias: list[float] = []
        meta_lock_flagged: list[bool] = []
        for seed in seeds:
            games = generate(replace(base, seed=seed))
            table = games.decisions
            wp = BaselineWinProb.fit(table).predict(table)
            for e in estimate(table, wp, WpaSettings(seed=seed)):
                truth = games.truth[(e.slot, e.option)]
                if e.slot == 3:
                    meta_lock_flagged.append(Flag.LOW_OVERLAP in e.flags and e.wpa is None)
                if e.wpa is None or e.ci is None:
                    continue
                errors.append(abs(e.wpa - truth))
                covered.append(e.ci[0] <= truth <= e.ci[1])
                if e.option == "A":
                    planted_bias.append(e.wpa - truth)
        metrics[f"synthetic.{name}.mean_abs_error"] = float(np.mean(errors))
        metrics[f"synthetic.{name}.max_abs_error"] = float(np.max(errors))
        metrics[f"synthetic.{name}.coverage"] = float(np.mean(covered))
        metrics[f"synthetic.{name}.planted_bias"] = float(np.mean(planted_bias))
        metrics[f"synthetic.{name}.meta_lock_flagged"] = float(np.mean(meta_lock_flagged))
    return metrics
