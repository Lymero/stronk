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
    pages: dict[tuple[str, str, int], tuple[RunePage, int]]
    """(champion, role, keystone) -> the page most played with that keystone, and its games."""
    spells: dict[Pick, list[tuple[tuple[int, int], int]]]
    """(champion, role) -> spell pairs, most played first: (spells in their usual order, games).
    A pair is the same whichever key each spell is on."""


def played(matches: Sequence[Match], statics: Mapping[str, StaticData]) -> Played:
    """Games whose patch has no static data, or with an unknown champion, are left out, as
    extract leaves them out."""
    games: Counter[Pick] = Counter()
    pages: dict[tuple[str, str, int], Counter[RunePage]] = {}
    pairs: dict[Pick, Counter[frozenset[int]]] = {}
    orders: dict[tuple[str, str, frozenset[int]], Counter[tuple[int, int]]] = {}
    for match in matches:
        static = statics.get(match.patch)
        if static is None:
            continue
        for p in match.participants:
            champion = static.champions.get(p.champion_id)
            if champion is None:
                continue
            pick = (champion.name, p.position)
            games[pick] += 1
            page = RunePage(p.primary_style, p.sub_style, (*p.perks, *p.stat_perks))
            pages.setdefault((*pick, p.keystone), Counter())[page] += 1
            pair = frozenset(p.spells)
            pairs.setdefault(pick, Counter())[pair] += 1
            orders.setdefault((*pick, pair), Counter())[p.spells] += 1
    # Most played first; ties go to the smallest, so the choice never depends on order.
    modal = {
        key: (page := min(c, key=lambda pg: (-c[pg], pg)), c[page]) for key, c in pages.items()
    }
    spells: dict[Pick, list[tuple[tuple[int, int], int]]] = {}
    for pick, counts in pairs.items():
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], sorted(kv[0])))
        spells[pick] = [(_usual(orders[(*pick, pair)]), n) for pair, n in ranked]
    return Played(games, modal, spells)


def _usual(orders: Counter[tuple[int, int]]) -> tuple[int, int]:
    return min(orders, key=lambda order: (-orders[order], order))
