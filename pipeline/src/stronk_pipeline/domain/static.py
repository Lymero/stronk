"""Game data for one patch (Data Dragon): champions and items, and how items are classified.

Decision points (docs/wpa-method.md, section 2) need to know which items complete a slot
and which ones start one. ADR-026 records the definitions:

- **completed item**: purchasable on Summoner's Rift, built from components, at least
  `COMPLETED_MIN_GOLD` in total, upgrades into nothing, and is not boots, a consumable, a
  trinket or champion-specific;
- **component**: anything in a completed item's recipe tree.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property

COMPLETED_MIN_GOLD = 2000
EXCLUDED_TAGS = frozenset({"Boots", "Consumable", "Trinket"})


@dataclass(frozen=True, slots=True)
class Champion:
    champion_id: int
    name: str
    """Data Dragon id, for example "MonkeyKing"."""
    tags: tuple[str, ...]
    """Classes, main one first: Fighter, Mage, Assassin, Tank, Marksman, Support."""
    attack: int
    """Data Dragon's 0-10 physical damage rating."""
    magic: int
    """Data Dragon's 0-10 magic damage rating."""

    @property
    def champion_class(self) -> str:
        return self.tags[0].lower() if self.tags else "unknown"


@dataclass(frozen=True, slots=True)
class Item:
    item_id: int
    name: str
    total_gold: int
    purchasable: bool
    on_rift: bool
    """Available on Summoner's Rift (map 11) and in the store."""
    tags: tuple[str, ...]
    builds_from: tuple[int, ...]
    builds_into: tuple[int, ...]
    champion_specific: bool = False


@dataclass(frozen=True)
class StaticData:
    version: str
    """Data Dragon version, for example "16.20.1"."""
    champions: Mapping[int, Champion]
    items: Mapping[int, Item]

    @cached_property
    def completed_items(self) -> frozenset[int]:
        return frozenset(i.item_id for i in self.items.values() if _is_completed(i))

    @cached_property
    def components(self) -> frozenset[int]:
        every = frozenset[int]().union(*self._recipe_trees.values())
        return every - self.completed_items

    @cached_property
    def _recipe_trees(self) -> Mapping[int, frozenset[int]]:
        return {i: self._tree(i) for i in self.completed_items}

    def recipe_tree(self, item_id: int) -> frozenset[int]:
        """Every component in a completed item's recipe, at any depth."""
        return self._recipe_trees.get(item_id, frozenset())

    def items_built_from(self, components: Iterable[int]) -> frozenset[int]:
        """Completed items whose recipe contains every one of `components`."""
        wanted = frozenset(components)
        return frozenset(i for i, tree in self._recipe_trees.items() if wanted <= tree)

    def _tree(self, item_id: int) -> frozenset[int]:
        found: set[int] = set()
        stack = list(self.items[item_id].builds_from)
        while stack:
            component = stack.pop()
            if component in found:
                continue
            found.add(component)
            item = self.items.get(component)
            if item is not None:
                stack.extend(item.builds_from)
        return frozenset(found)


def _is_completed(item: Item) -> bool:
    return (
        item.purchasable
        and item.on_rift
        and not item.champion_specific
        and bool(item.builds_from)
        and not item.builds_into
        and item.total_gold >= COMPLETED_MIN_GOLD
        and not EXCLUDED_TAGS.intersection(item.tags)
    )
