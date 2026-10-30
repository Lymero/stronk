"""Where players make the choices we score (docs/wpa-method.md, section 2; ADR-026).

- Slot 0, champion select: the keystone rune.
- The start (slot `START_SLOT`, ADR-071): the items bought before `STARTING_PURCHASES_MS`,
  without supplies (consumables and trinkets: potions, wards), as one option `"a,b"` (ids
  sorted, each once): a jungle pet, a Doran's item, Cull, Dark Seal... Anchored at the first of
  those purchases. A start of supplies alone adds nothing.
- The first components (slot `COMPONENTS_SLOT`, ADR-072): what is bought on the first trip back
  to base, the purchases within `TRIP_MS` of the first one after the start, without supplies,
  boots or completed items, as one option the same way: Dark Seal and Amplifying Tome, a Long
  Sword... Anchored at that first purchase. Boots are their own decision.
- Champion select, the rest of the rune page (ADR-057), one decision each: every row of the
  primary tree (slot `tree * 10 + row`, rows 1 to 3, option the rune), the secondary tree's two
  runes as a pair (slot `tree * 10 + 5`, option `"low,high"`), and every stat shard row (slot
  `50000 + row`). A row only compares runes of the same tree, as the client offers them.
- Slot k from 1 to 3: the k-th completed item. The decision is anchored at the first component
  bought after slot k - 1 was completed (for slot 1, after the starting purchases), so every option
  is compared from the state the player was in when they started building it.
- Slot 4, the late items (ADR-067): the fourth completed item and every later one, up to the
  seventh (bot laners can carry a seventh), each its own decision anchored the same way. Late
  items are bought for the game at hand rather than in a set order, and one slot at a time they
  split too few games to compare.

A slot still unfinished when the game ends keeps its decision if the components bought so far
point to exactly one completed item; otherwise it is dropped and counted, so the report shows
how many late decisions are lost.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from stronk_pipeline.domain.match import ItemEvent, Match
from stronk_pipeline.domain.static import StaticData

STARTING_PURCHASES_MS = 90_000
"""Purchases before this are the starting items, not a decision about slot 1."""
LATE_SLOT = 4
"""The slot of the fourth completed item and every later one (ADR-067)."""
MAX_SLOT = LATE_SLOT
MAX_ITEMS = 7
"""Completed items followed per player."""
SECONDARY_ROW = 5
"""`tree * 10 + SECONDARY_ROW` is the secondary pair's slot."""
SHARD_SLOTS = 50_000
"""`SHARD_SLOTS + row` is a stat shard row's slot."""
START_SLOT = 60_000
"""The starting items' slot (ADR-071)."""
COMPONENTS_SLOT = 60_001
"""The first components' slot (ADR-072)."""
PURCHASE_SLOTS = range(START_SLOT, START_SLOT + 10)
"""The slots of purchases measured as a set of items: the start, the first components."""
TRIP_MS = 30_000
"""Purchases within this of a trip's first one are bought on the same trip back."""


def is_tree(tree: int) -> bool:
    """A rune tree id (8000 to 8400 today). The API sometimes sends 0 for a tree, which would
    encode as an item slot, so such a tree's rows are left out; so is one that would land on
    the shard slots."""
    return tree >= 1_000 and tree not in (SHARD_SLOTS // 10, START_SLOT // 10)


def rune_slot(tree: int, row: int) -> int:
    """A primary tree's row (1 to 3), or its secondary pair (`SECONDARY_ROW`)."""
    return tree * 10 + row


def is_rune_slot(slot: int) -> bool:
    """Champion select's choices besides the keystone: rune rows, secondary pairs, shards."""
    return slot > MAX_SLOT and slot not in PURCHASE_SLOTS


def rune_row(slot: int) -> tuple[str, int | None, int | None]:
    """A rune slot as (kind, tree, row): `("primary", 8000, 1)`, `("secondary", 8100, None)`,
    `("shard", None, 2)`."""
    if SHARD_SLOTS < slot < SHARD_SLOTS + 10:
        return ("shard", None, slot - SHARD_SLOTS)
    tree, row = divmod(slot, 10)
    return ("secondary", tree, None) if row == SECONDARY_ROW else ("primary", tree, row)


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    participant_id: int
    slot: int
    timestamp: int
    option: str
    inferred: bool = False
    """The slot was unfinished; the option comes from its components."""


def decision_points(match: Match, static: StaticData, dropped: Counter[str]) -> list[DecisionPoint]:
    points = [DecisionPoint(p.participant_id, 0, 0, str(p.keystone)) for p in match.participants]
    for p in match.participants:
        points.extend(
            _rune_rows(p.participant_id, p.primary_style, p.sub_style, p.perks, p.stat_perks)
        )
    for participant in match.participants:
        purchases = kept_purchases(match.items, participant.participant_id)
        for slot, bought in (
            (START_SLOT, starting_items(purchases, static)),
            (COMPONENTS_SLOT, first_components(purchases, static)),
        ):
            if bought.option:
                points.append(
                    DecisionPoint(participant.participant_id, slot, bought.at, bought.option)
                )
        points.extend(_item_slots(participant.participant_id, purchases, static, dropped))
    return points


@dataclass(frozen=True, slots=True)
class Purchase:
    """Items bought at once and measured as one choice: the start (ADR-071), the first
    components (ADR-072)."""

    option: str
    """What is measured: the items that count, ids sorted, each once; "" for none."""
    bought: tuple[int, ...]
    """Everything bought, supplies included, sorted, repeats kept: what the import writes."""
    at: int
    """The first purchase that counts, in ms (0 without one)."""


def _purchase(bought: list[ItemEvent], counts: Callable[[int], bool]) -> Purchase:
    kept = [p for p in bought if counts(p.item_id)]
    option = ",".join(str(i) for i in sorted({p.item_id for p in kept}))
    every = tuple(sorted(p.item_id for p in bought))
    return Purchase(option, every, kept[0].timestamp if kept else 0)


def starting_items(purchases: list[ItemEvent], static: StaticData) -> Purchase:
    """The purchases before `STARTING_PURCHASES_MS`, undone ones already left out; supplies
    don't count."""
    early = [p for p in purchases if p.timestamp < STARTING_PURCHASES_MS]
    return _purchase(early, lambda i: not static.is_supply(i))


def first_components(purchases: list[ItemEvent], static: StaticData) -> Purchase:
    """The first trip back's purchases (ADR-072): from the first purchase after the start that
    counts (not a supply, boots or a completed item) to `TRIP_MS` after it. What is bought with
    it, supplies and boots included, is what the import writes."""

    def counts(i: int) -> bool:
        return not (static.is_supply(i) or static.is_boots(i) or i in static.completed_items)

    later = [p for p in purchases if p.timestamp >= STARTING_PURCHASES_MS]
    first = next((p for p in later if counts(p.item_id)), None)
    if first is None:
        return Purchase("", (), 0)
    return _purchase(
        [p for p in later if first.timestamp <= p.timestamp < first.timestamp + TRIP_MS], counts
    )


def _rune_rows(
    participant_id: int,
    primary: int,
    secondary: int,
    perks: tuple[int, ...],
    shards: tuple[int, ...],
) -> list[DecisionPoint]:
    """The page after its keystone: perks are the keystone, three primary runes in row order,
    then two secondary runes; a page that isn't whole adds nothing."""
    if len(perks) != 6 or len(shards) != 3:
        return []
    rows: list[DecisionPoint] = []
    if is_tree(primary):
        rows.extend(
            DecisionPoint(participant_id, rune_slot(primary, row), 0, str(rune))
            for row, rune in enumerate(perks[1:4], start=1)
        )
    if is_tree(secondary):
        pair = ",".join(str(r) for r in sorted(perks[4:6]))
        rows.append(DecisionPoint(participant_id, rune_slot(secondary, SECONDARY_ROW), 0, pair))
    rows.extend(
        DecisionPoint(participant_id, SHARD_SLOTS + row, 0, str(shard))
        for row, shard in enumerate(shards, start=1)
    )
    return rows


def kept_purchases(events: tuple[ItemEvent, ...], participant_id: int) -> list[ItemEvent]:
    """Purchases in order, without the ones the player undid."""
    kept: list[ItemEvent] = []
    for event in events:
        if event.participant_id != participant_id:
            continue
        if event.action == "purchased":
            kept.append(event)
        elif event.action == "undo" and event.item_id != 0:
            for i in range(len(kept) - 1, -1, -1):
                if kept[i].item_id == event.item_id:
                    del kept[i]
                    break
    return kept


def _item_slots(
    participant_id: int,
    purchases: list[ItemEvent],
    static: StaticData,
    dropped: Counter[str],
) -> list[DecisionPoint]:
    points: list[DecisionPoint] = []
    started: int | None = None
    components: list[int] = []
    for purchase in purchases:
        if len(points) == MAX_ITEMS:
            return points
        if not points and purchase.timestamp < STARTING_PURCHASES_MS:
            continue
        if purchase.item_id in static.completed_items:
            anchor = started if started is not None else purchase.timestamp
            points.append(
                DecisionPoint(participant_id, _slot(len(points)), anchor, str(purchase.item_id))
            )
            started, components = None, []
        elif purchase.item_id in static.components:
            started = purchase.timestamp if started is None else started
            components.append(purchase.item_id)
    if started is not None and len(points) < MAX_ITEMS:
        candidates = static.items_built_from(components)
        if len(candidates) == 1:
            (option,) = candidates
            slot = _slot(len(points))
            points.append(DecisionPoint(participant_id, slot, started, str(option), inferred=True))
        else:
            dropped["unfinished_slot"] += 1
    return points


def _slot(completed: int) -> int:
    """The slot of the item completed after `completed` others: 1 to 3, then the late slot."""
    return min(completed + 1, LATE_SLOT)
