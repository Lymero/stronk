"""Synthetic games with planted effects, hidden skill and situational buying.

Each game follows one player of a single champion through three decision points:

| Slot | Options | Who chooses what | True effect |
|---|---|---|---|
| 1 | A or C | skilled players pick A more (hidden skill confounds) | A +2%, C 0 |
| 2 | B or D | players who are ahead pick B (situational buying) | both 0 |
| 3 | E or F | E almost always (meta-locked, ~97%) | both 0 |

Hidden skill raises the gold lead over time and the chance of winning directly. The
pipeline only sees the gold lead at each decision and a noisy skill proxy (the crawl-derived
prior win rate), never skill itself. Effects are added on the probability scale, so "A adds
+2%" holds exactly, apart from clipping at the extremes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats, expit

CHAMPION = "Synthion"
CHAMPION_CLASS = "fighter"
ROLE = "TOP"
FEATURES = ("gold_diff", "skill_proxy")


@dataclass(frozen=True)
class SlotSpec:
    slot: int
    minute: float
    options: tuple[str, str]
    """(first, second); the choice model gives P(first)."""
    effects: tuple[float, float]


SLOTS = (
    SlotSpec(1, 8.0, ("A", "C"), (0.02, 0.0)),
    SlotSpec(2, 16.0, ("B", "D"), (0.0, 0.0)),
    SlotSpec(3, 24.0, ("E", "F"), (0.0, 0.0)),
)


@dataclass(frozen=True)
class SynthConfig:
    games: int = 40_000
    seed: int = 7
    hidden_skill_choice: float = 0.6
    """Log-odds of picking A per unit of hidden skill. 0 removes the hidden confounder."""
    situational_buying: float = 1.5
    """Log-odds of picking B per 1k gold of lead."""
    meta_lock_logit: float = 3.5
    """Log-odds of picking E: 3.5 gives about 97%."""
    skill_proxy_noise: float = 0.3
    skill_gold_drift: float = 0.3
    """Gold lead (k) gained per unit of skill between decisions."""
    skill_win: float = 0.3
    """Direct log-odds of winning per unit of skill, beyond the gold lead."""
    gold_win: float = 0.5
    """Log-odds of winning per 1k gold of final lead."""


@dataclass(frozen=True)
class SynthGames:
    config: SynthConfig
    decisions: DecisionTable
    truth: dict[tuple[int, str], float] = field(default_factory=dict[tuple[int, str], float])
    """(slot, option) -> true effect versus the alternatives, as the estimand defines it."""


def generate(config: SynthConfig) -> SynthGames:
    rng = np.random.default_rng(config.seed)
    n = config.games
    skill = rng.normal(size=n)
    proxy = skill + rng.normal(scale=config.skill_proxy_noise, size=n)

    gold = np.zeros(n)
    gold_at: list[Floats] = []
    for _ in SLOTS:
        gold = gold + config.skill_gold_drift * skill + rng.normal(size=n)
        gold_at.append(gold)
    final_gold = gold + config.skill_gold_drift * skill + rng.normal(size=n)

    picks_first: list[NDArray[np.bool_]] = []
    for spec, gold_now in zip(SLOTS, gold_at, strict=True):
        logit = _choice_logit(spec.slot, config, skill, gold_now)
        picks_first.append(rng.random(n) < expit(logit))

    base = expit(config.gold_win * final_gold + config.skill_win * skill)
    added = sum(
        (
            np.where(first, spec.effects[0], spec.effects[1])
            for spec, first in zip(SLOTS, picks_first, strict=True)
        ),
        start=np.zeros(n),
    )
    p_win = np.clip(base + added, 0.01, 0.99)
    win = (rng.random(n) < p_win).astype(np.int64)

    decisions = _table(config, proxy, gold_at, picks_first, win)
    truth = _truth(base, picks_first)
    return SynthGames(config, decisions, truth)


def _choice_logit(slot: int, config: SynthConfig, skill: Floats, gold: Floats) -> Floats:
    if slot == 1:
        return config.hidden_skill_choice * skill + 0.3 * gold
    if slot == 2:
        return config.situational_buying * gold
    return np.full(len(skill), config.meta_lock_logit)


def _table(
    config: SynthConfig,
    proxy: Floats,
    gold_at: list[Floats],
    picks_first: list[NDArray[np.bool_]],
    win: NDArray[np.int64],
) -> DecisionTable:
    n = config.games
    k = len(SLOTS)
    match_ids = np.array([f"SYN_{config.seed}_{i}" for i in range(n)])
    options = [np.where(first, spec.options[0], spec.options[1]) for spec, first in
               zip(SLOTS, picks_first, strict=True)]  # fmt: skip
    return DecisionTable.create(
        match_id=np.tile(match_ids, k),
        participant=np.ones(n * k, dtype=np.int64),
        champion=np.full(n * k, CHAMPION),
        champion_class=np.full(n * k, CHAMPION_CLASS),
        role=np.full(n * k, ROLE),
        slot=np.repeat([s.slot for s in SLOTS], n).astype(np.int64),
        minute=np.repeat([s.minute for s in SLOTS], n).astype(np.float64),
        option=np.concatenate(options),
        outcome=np.tile(win, k),
        features=np.column_stack([np.concatenate(gold_at), np.tile(proxy, k)]),
        feature_names=FEATURES,
    )


def _truth(base: Floats, picks_first: list[NDArray[np.bool_]]) -> dict[tuple[int, str], float]:
    """Mean over decisions of P(win | option) - P(win | the alternative), other slots as chosen."""
    truth: dict[tuple[int, str], float] = {}
    for j, spec in enumerate(SLOTS):
        others = sum(
            (
                np.where(first, s.effects[0], s.effects[1])
                for i, (s, first) in enumerate(zip(SLOTS, picks_first, strict=True))
                if i != j
            ),
            start=np.zeros(len(base)),
        )
        p_first = np.clip(base + others + spec.effects[0], 0.01, 0.99)
        p_second = np.clip(base + others + spec.effects[1], 0.01, 0.99)
        diff = float(np.mean(p_first - p_second))
        truth[(spec.slot, spec.options[0])] = diff
        truth[(spec.slot, spec.options[1])] = -diff
    return truth
