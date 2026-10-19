"""Types shared by every WPA estimator version."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Flag(StrEnum):
    """docs/wpa-method.md, section 7. Values match the published contract."""

    LOW_SAMPLE = "low_sample"
    LOW_OVERLAP = "low_overlap"
    NO_CLEAR_DIFFERENCE = "no_clear_difference"
    FRAGILE = "fragile"


@dataclass(frozen=True)
class WpaSettings:
    overlap_epsilon: float = 0.05
    """Option A's overlap population: decisions where P(A) lies in [epsilon, 1 - epsilon]."""
    min_overlap_share: float = 0.5
    """An option with fewer of its decisions inside the overlap population gets `low_overlap`."""
    min_decisions: int = 300
    """Fewer overlap decisions than this gets `low_sample`."""
    min_estimate_decisions: int = 30
    """Fewer overlap decisions than this, for the option or for its alternatives: no number at
    all, only `low_sample`. A bootstrap over a handful of matches can't measure its own
    uncertainty (one decision against one gives a zero-width interval)."""
    bootstrap_samples: int = 200
    confidence: float = 0.95
    fdr: float = 0.05
    """False discovery rate for calling a contrast clear (Benjamini-Hochberg, ADR-036)."""
    min_shrinkage_group: int = 3
    """Champions needed in a (class, role, slot, option) group before shrinking toward it."""
    seed: int = 0


@dataclass(frozen=True)
class OptionEstimate:
    champion: str
    champion_class: str
    role: str
    slot: int
    option: str
    wpa: float | None
    """Effect on win probability of choosing this option instead of the alternatives."""
    ci: tuple[float, float] | None
    n: int
    """Decisions choosing this option inside the overlap population (all of them if none are)."""
    flags: frozenset[Flag] = field(default_factory=frozenset[Flag])
    q: float | None = None
    """Benjamini-Hochberg adjusted p-value of no difference with `versus` (ADR-036); None for
    the most played option and for options not eligible to be claimed."""
    versus: str | None = None
    """The point's most played eligible option, which `q` compares this one with."""
    contrast: float | None = None
    """Effect of this option against `versus` (head to head, the estimator's effect)."""
    contrast_ci: tuple[float, float] | None = None
    """Bootstrap interval of `contrast`, at the run's confidence."""
    chosen: int = 0
    """Decisions choosing this option at its point, inside the overlap or not (popularity)."""
