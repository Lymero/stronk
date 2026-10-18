"""Synthetic games with planted effects, hidden skill and situational buying.

Each game follows one player of a single champion through four decision points:

| Slot | Options | Who chooses what | True effect |
|---|---|---|---|
| 1 | A or C | skilled players pick A more (hidden skill confounds) | A +2%, C 0 |
| 2 | B or D | players who are ahead pick B (situational buying) | both 0 |
| 3 | E or F | E almost always (meta-locked, ~97%) | both 0 |
| 4 | G, H, I, J, rare T1-T8 | G when ahead, I when behind; each T about 0.1% | G +3%, rest 0 |

Slot 4 is what real decision points look like: a few common options and many rare ones. The rare
ones must get `low_overlap` without taking the common options' numbers with them (ADR-035).

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
    options: tuple[str, ...]
    """The choice model gives one log-odds column per option."""
    effects: tuple[float, ...]


TAIL = tuple(f"T{i}" for i in range(1, 9))
SLOTS = (
    SlotSpec(1, 8.0, ("A", "C"), (0.02, 0.0)),
    SlotSpec(2, 16.0, ("B", "D"), (0.0, 0.0)),
    SlotSpec(3, 24.0, ("E", "F"), (0.0, 0.0)),
    SlotSpec(4, 30.0, ("G", "H", "I", "J", *TAIL), (0.03, 0.0, 0.0, 0.0, *(0.0,) * len(TAIL))),
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
    tail_logit: float = -5.5
    """Log-odds of each tail option against H (or J) at slot 4: -5.5 gives about 0.1% each."""
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

    # Slot 4 draws from its own stream, so slots 1-3 are the same games as before it existed.
    tail_rng = np.random.default_rng([config.seed, 4])
    streams = [rng, rng, rng, tail_rng]

    gold = np.zeros(n)
    gold_at: list[Floats] = []
    for _, stream in zip(SLOTS[:3], streams, strict=False):
        gold = gold + config.skill_gold_drift * skill + stream.normal(size=n)
        gold_at.append(gold)
    final_gold = gold + config.skill_gold_drift * skill + rng.normal(size=n)
    gold_at.append(gold_at[2] + config.skill_gold_drift * skill + tail_rng.normal(size=n))

    picks: list[NDArray[np.intp]] = []
    choice_probs: list[Floats] = []
    for spec, gold_now, stream in zip(SLOTS, gold_at, streams, strict=True):
        logits = _choice_logits(spec.slot, config, skill, gold_now)
        odds = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = odds / odds.sum(axis=1, keepdims=True)
        choice_probs.append(probs)
        cumulative = np.cumsum(probs, axis=1)
        drawn = (stream.random((n, 1)) > cumulative).sum(axis=1)
        picks.append(np.minimum(drawn, len(spec.options) - 1))

    base = expit(config.gold_win * final_gold + config.skill_win * skill)
    added = sum(
        (np.asarray(spec.effects)[pick] for spec, pick in zip(SLOTS, picks, strict=True)),
        start=np.zeros(n),
    )
    p_win = np.clip(base + added, 0.01, 0.99)
    win = (rng.random(n) < p_win).astype(np.int64)

    decisions = _table(config, proxy, gold_at, picks, win)
    truth = _truth(base, picks, choice_probs)
    return SynthGames(config, decisions, truth)


def _choice_logits(slot: int, config: SynthConfig, skill: Floats, gold: Floats) -> Floats:
    """(games, options) log-odds; the second column is the reference (0) for slots 1-3."""
    zero = np.zeros(len(skill))
    if slot == 1:
        return np.column_stack([config.hidden_skill_choice * skill + 0.3 * gold, zero])
    if slot == 2:
        return np.column_stack([config.situational_buying * gold, zero])
    if slot == 3:
        return np.column_stack([np.full(len(skill), config.meta_lock_logit), zero])
    tail = [np.full(len(skill), config.tail_logit)] * len(TAIL)
    return np.column_stack([0.5 * gold, zero, -0.5 * gold, zero, *tail])


def _table(
    config: SynthConfig,
    proxy: Floats,
    gold_at: list[Floats],
    picks: list[NDArray[np.intp]],
    win: NDArray[np.int64],
) -> DecisionTable:
    n = config.games
    k = len(SLOTS)
    match_ids = np.array([f"SYN_{config.seed}_{i}" for i in range(n)])
    options = [np.asarray(spec.options)[pick] for spec, pick in zip(SLOTS, picks, strict=True)]
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


def _truth(
    base: Floats, picks: list[NDArray[np.intp]], choice_probs: list[Floats]
) -> dict[tuple[int, str], float]:
    """Mean over decisions of P(win | option) - P(win | the alternative), other slots as chosen.

    The alternative is what this player would choose instead, in this situation: each other
    option weighted by its choice probability at this decision (docs/wpa-method.md, section 2:
    every option is compared from the same game state). With two options it is the other one.
    """
    truth: dict[tuple[int, str], float] = {}
    effects = [np.asarray(spec.effects) for spec in SLOTS]
    for j, spec in enumerate(SLOTS):
        others = sum(
            (effects[i][pick] for i, pick in enumerate(picks) if i != j),
            start=np.zeros(len(base)),
        )
        p = np.clip((base + others)[:, None] + effects[j][None, :], 0.01, 0.99)
        for k, option in enumerate(spec.options):
            alternatives = choice_probs[j].copy()
            alternatives[:, k] = 0.0
            weights = alternatives / alternatives.sum(axis=1, keepdims=True)
            truth[(spec.slot, option)] = float(np.mean(p[:, k] - (p * weights).sum(axis=1)))
    return truth
