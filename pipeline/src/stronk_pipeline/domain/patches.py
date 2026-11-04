"""Patches in order, and the items each one changed: what pooling several patches needs
(ADR-088). An item changed between a game's patch and the newest is measured on the newest
patch's games only, and published with the patch that changed it."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping

from stronk_pipeline.domain.static import StaticData


class MissingFingerprintsError(ValueError):
    """Game data stored before item fingerprints were kept: changes can't be told."""


def patch_key(patch: str) -> tuple[int, ...]:
    """ "16.9" before "16.10": a patch's numbers, compared as numbers."""
    return tuple(int(n) for n in patch.split("."))


def in_order(patches: Iterable[str]) -> list[str]:
    """Each patch once, oldest first."""
    return sorted(set(patches), key=patch_key)


def changed_items(old: StaticData, new: StaticData) -> frozenset[int]:
    """Items in both patches whose description, stats or cost differ."""
    for static in (old, new):
        if any(not i.fingerprint for i in static.items.values()):
            raise MissingFingerprintsError(
                f"game data {static.version} has no item fingerprints: refresh it "
                "(tools/refresh_static.py)"
            )
    return frozenset(
        i
        for i, item in old.items.items()
        if i in new.items and new.items[i].fingerprint != item.fingerprint
    )


def changed_since(
    statics: Mapping[str, StaticData], patches: Iterable[str]
) -> dict[str, frozenset[int]]:
    """For each of `patches` but the newest: the items changed between it and the newest (an
    item changed and then changed back counts as unchanged). One patch: nothing."""
    ordered = in_order(patches)
    newest = statics[ordered[-1]]
    return {p: changed_items(statics[p], newest) for p in ordered[:-1]}


def changed_in(statics: Mapping[str, StaticData], patches: Iterable[str]) -> dict[int, str]:
    """Each item changed within `patches`, and the latest of them that changed it."""
    ordered = in_order(patches)
    found: dict[int, str] = {}
    for earlier, later in itertools.pairwise(ordered):
        for item in changed_items(statics[earlier], statics[later]):
            found[item] = later
    return found
