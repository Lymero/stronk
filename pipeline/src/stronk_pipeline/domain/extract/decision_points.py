"""Where players make the choices we score (docs/wpa-method.md, section 2; ADR-026).

- Slot 0, champion select: the keystone rune.
- Slot k >= 1: the k-th completed item. The decision is anchored at the first component bought
  after slot k - 1 was completed (for slot 1, after the starting purchases), so every option
  is compared from the state the player was in when they started building it.

A slot still unfinished when the game ends keeps its decision if the components bought so far
point to exactly one completed item; otherwise it is dropped and counted, so the report shows
how many late decisions are lost.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from stronk_pipeline.domain.match import ItemEvent, Match
from stronk_pipeline.domain.static import StaticData

STARTING_PURCHASES_MS = 90_000
"""Purchases before this are the starting items, not a decision about slot 1."""
MAX_SLOT = 6


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
    for participant in match.participants:
        purchases = _kept_purchases(match.items, participant.participant_id)
        points.extend(_item_slots(participant.participant_id, purchases, static, dropped))
    return points


def _kept_purchases(events: tuple[ItemEvent, ...], participant_id: int) -> list[ItemEvent]:
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
        if len(points) == MAX_SLOT:
            return points
        if not points and purchase.timestamp < STARTING_PURCHASES_MS:
            continue
        if purchase.item_id in static.completed_items:
            anchor = started if started is not None else purchase.timestamp
            points.append(
                DecisionPoint(participant_id, len(points) + 1, anchor, str(purchase.item_id))
            )
            started, components = None, []
        elif purchase.item_id in static.components:
            started = purchase.timestamp if started is None else started
            components.append(purchase.item_id)
    if started is not None and len(points) < MAX_SLOT:
        candidates = static.items_built_from(components)
        if len(candidates) == 1:
            (option,) = candidates
            slot = len(points) + 1
            points.append(DecisionPoint(participant_id, slot, started, str(option), inferred=True))
        else:
            dropped["unfinished_slot"] += 1
    return points
