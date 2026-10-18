"""What `publish` needs from crawled games besides the estimates: how many games each champion
and role has, and the full rune page that goes with each keystone.

WPA estimates the keystone (decision slot 0); a published rune option is a whole page. For each
champion, role and keystone, the page published is the one most often played with it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.static import StaticData

type Pick = tuple[str, str]
"""(champion name, role)."""


@dataclass(frozen=True, slots=True, order=True)
class RunePage:
    primary_style: int
    sub_style: int
    perks: tuple[int, ...]
    """Every selected rune, primary tree first, then the three stat shards: nine in all."""


@dataclass(frozen=True)
class Played:
    games: Counter[Pick]
    pages: dict[tuple[str, str, int], RunePage]
    """(champion, role, keystone) -> the page most played with that keystone."""


def played(matches: Sequence[Match], statics: Mapping[str, StaticData]) -> Played:
    """Games whose patch has no static data, or with an unknown champion, are left out, as
    extract leaves them out."""
    games: Counter[Pick] = Counter()
    pages: dict[tuple[str, str, int], Counter[RunePage]] = {}
    for match in matches:
        static = statics.get(match.patch)
        if static is None:
            continue
        for p in match.participants:
            champion = static.champions.get(p.champion_id)
            if champion is None:
                continue
            games[(champion.name, p.position)] += 1
            page = RunePage(p.primary_style, p.sub_style, (*p.perks, *p.stat_perks))
            key = (champion.name, p.position, p.keystone)
            pages.setdefault(key, Counter())[page] += 1
    # Most played first; ties go to the smallest page, so the choice never depends on order.
    modal = {key: min(c, key=lambda page: (-c[page], page)) for key, c in pages.items()}
    return Played(games, modal)
