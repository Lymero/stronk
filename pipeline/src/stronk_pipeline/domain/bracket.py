"""Elo brackets (ADR-076, ADR-079): which ranked tiers a build's games come from, as the published
data names them (`{patch}/{region}/{elo}/...`).

A crawl seeds players from the ladder of one band of tiers and keeps their games, so its games are
those of players in that band (lobbies mix ranks a little at the edges): Master+ (Challenger,
Grandmaster, Master), Diamond or Emerald. A published bracket is a band with every band above it,
as players read "Diamond+": Master+, Diamond+ (Diamond and Master+), Emerald+ (all three). The
bands' games pool because their estimates differ no more than noise explains (ADR-079).
"""

from __future__ import annotations

from collections.abc import Sequence

MASTER_PLUS = "master_plus"
DIAMOND = "diamond"
EMERALD = "emerald"
BANDS = (MASTER_PLUS, DIAMOND, EMERALD)
"""A crawl's bands of tiers, highest first."""
APEX = ("CHALLENGER", "GRANDMASTER", "MASTER")
DIVIDED = ("DIAMOND", "EMERALD")
"""Tiers read by division and page; an apex league comes whole."""
LEGACY = MASTER_PLUS
"""A crawl from before bands were recorded: every one of them crawled the apex tiers."""

BRACKETS: dict[str, tuple[str, ...]] = {
    "master_plus": (MASTER_PLUS,),
    "diamond_plus": (MASTER_PLUS, DIAMOND),
    "emerald_plus": (MASTER_PLUS, DIAMOND, EMERALD),
}
"""The published brackets, highest first, and the bands each one pools."""


def bracket_of(tiers: Sequence[str]) -> str | None:
    """The band of a crawl's tiers: Master+ for apex tiers only, Diamond or Emerald alone; None
    when they mix two."""
    if tiers and all(t in APEX for t in tiers):
        return MASTER_PLUS
    for tier, band in (("DIAMOND", DIAMOND), ("EMERALD", EMERALD)):
        if tiers and all(t == tier for t in tiers):
            return band
    return None


def ordered(bands: Sequence[str]) -> list[str]:
    """`bands` once each, highest first."""
    return [b for b in BANDS if b in bands]


def published(bands: Sequence[str]) -> str | None:
    """The bracket that pools exactly these bands; None when they don't make one (a band
    missing above another, or none at all)."""
    held = set(bands)
    return next((name for name, pooled in BRACKETS.items() if held == set(pooled)), None)
