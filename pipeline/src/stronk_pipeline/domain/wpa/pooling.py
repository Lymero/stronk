"""Class-level decision points: every champion of a class at one point (ADR-039).

Pooling, say, every marksman's second item multiplies the decisions per point. Champion is a
confounder there (some champions both favour an item and win more), handled twice: each
champion is a feature, so the propensity and overlap are within champion, and champion is a
stratum, so event scores are centred within champion at each point (champion fixed effects)
before options are compared.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionTable

CHAMPION_PREFIX = "champion="


@dataclass(frozen=True)
class Pooled:
    table: DecisionTable
    order: NDArray[np.intp]
    """Row k of `table` is row `order[k]` of the input: reorder WP and outcomes with it."""
    strata: NDArray[np.str_]
    """Each row's champion."""


def pool_by_class(table: DecisionTable) -> Pooled:
    """`champion` becomes the class; one 0/1 feature per champion (all but the first)."""
    champions = sorted(set(table.champion.tolist()))[1:]
    indicators = np.zeros((len(table), len(champions)))
    for j, champion in enumerate(champions):
        indicators[:, j] = table.champion == champion
    pooled = DecisionTable(
        table.match_id,
        table.participant,
        table.champion_class,
        table.champion_class,
        table.role,
        table.slot,
        table.minute,
        table.option,
        table.outcome,
        np.column_stack([table.features, indicators]),
        (*table.feature_names, *(CHAMPION_PREFIX + c for c in champions)),
    )
    # Canonical order for the new champion column. A participant plays one champion per game,
    # so no two rows share (class, role, slot, match, participant) and none is dropped.
    order = np.lexsort(
        (pooled.participant, pooled.match_id, pooled.slot, pooled.role, pooled.champion)
    )
    return Pooled(pooled.take(order), order, table.champion[order])
