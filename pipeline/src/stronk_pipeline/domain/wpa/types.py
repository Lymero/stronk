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
    """Decisions where any option's propensity is below this are outside the overlap population."""
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
