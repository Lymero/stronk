"""Elo brackets (ADR-076): which ranked tiers a crawl's games come from, as the published data
names them (`{patch}/{region}/{elo}/...`).

A crawl seeds players from the ladder of its tiers and keeps their games, so its games are those
of players in that bracket (lobbies mix ranks a little at the edges). One crawl holds one bracket,
and nothing mixes two: extract and publish refuse it.
"""

from __future__ import annotations

from collections.abc import Sequence

MASTER_PLUS = "master_plus"
DIAMOND = "diamond"
APEX = ("CHALLENGER", "GRANDMASTER", "MASTER")
LEGACY = MASTER_PLUS
"""A crawl from before brackets were recorded: every one of them crawled the apex tiers."""


def single(brackets: Sequence[str]) -> str | None:
    """The one bracket several crawls share; None when they hold two (or none are given)."""
    return brackets[0] if brackets and all(b == brackets[0] for b in brackets) else None


def bracket_of(tiers: Sequence[str]) -> str | None:
    """The bracket of a crawl's tiers: Master+ for apex tiers only, Diamond for Diamond alone;
    None when they mix the two."""
    if tiers and all(t in APEX for t in tiers):
        return MASTER_PLUS
    if tiers and all(t == "DIAMOND" for t in tiers):
        return DIAMOND
    return None
