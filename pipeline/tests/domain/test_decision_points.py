from collections import Counter
from dataclasses import replace

from riot_builders import Json, buy, domain_match, domain_static, undo

from stronk_pipeline.domain.extract.decision_points import (
    MAX_SLOT,
    DecisionPoint,
    decision_points,
    is_rune_slot,
)

STATIC = domain_static()
MIN = 60_000


def items_of(
    events: list[Json], participant_id: int = 1
) -> tuple[list[DecisionPoint], Counter[str]]:
    dropped: Counter[str] = Counter()
    points = decision_points(domain_match(events=events), STATIC, dropped)
    return [
        p for p in points if p.participant_id == participant_id and 1 <= p.slot <= MAX_SLOT
    ], dropped


def test_every_player_has_a_keystone_decision_in_champion_select() -> None:
    points = decision_points(domain_match(), STATIC, Counter())
    keystones = [p for p in points if p.slot == 0]
    assert len(keystones) == 10
    assert keystones[0] == DecisionPoint(1, 0, 0, "8010")


def test_the_rest_of_the_page_is_one_decision_per_row() -> None:
    """Rows of the primary tree, the secondary pair and each shard row, all at the start."""
    points = decision_points(domain_match(), STATIC, Counter())
    page = [p for p in points if p.participant_id == 1 and is_rune_slot(p.slot)]
    primary = next(p for p in points if p.participant_id == 1 and p.slot == 0)
    assert primary.option == "8010"
    assert [(p.slot, p.option) for p in page] == [
        (81001, "8139"),
        (81002, "8138"),
        (81003, "8135"),
        (83005, "8345,8347"),
        (50001, "5008"),
        (50002, "5008"),
        (50003, "5011"),
    ]
    assert {p.timestamp for p in page} == {0}
    assert sum(1 for p in points if is_rune_slot(p.slot)) == 70


def test_a_missing_tree_adds_no_rows_and_never_an_item_slot() -> None:
    """Regression: the API sent a secondary tree of 0 (9 of 229,540 players on 16.20), whose
    pair encoded as slot 5, an item slot, and broke publish."""
    match = domain_match()
    first = replace(match.participants[0], sub_style=0)
    points = decision_points(
        replace(match, participants=(first, *match.participants[1:])), STATIC, Counter()
    )
    mine = [p for p in points if p.participant_id == 1]
    assert all(p.slot == 0 or is_rune_slot(p.slot) for p in mine)
    assert [p.slot for p in mine if is_rune_slot(p.slot)] == [
        81001,
        81002,
        81003,
        50001,
        50002,
        50003,
    ]


def test_slot_is_anchored_at_the_first_component() -> None:
    points, _ = items_of([buy(4 * MIN, 1, 1036), buy(6 * MIN, 1, 1036), buy(9 * MIN, 1, 3071)])
    assert points == [DecisionPoint(1, 1, 4 * MIN, "3071")]


def test_starting_items_consumables_and_boots_do_not_anchor() -> None:
    events = [
        buy(1_000, 1, 1036),  # starting purchase, even though it is a component
        buy(2_000, 1, 2003),
        buy(3 * MIN, 1, 2003),
        buy(4 * MIN, 1, 1001),
        buy(5 * MIN, 1, 1037),
        buy(8 * MIN, 1, 6333),
    ]
    points, _ = items_of(events)
    assert points == [DecisionPoint(1, 1, 5 * MIN, "6333")]


def test_next_slot_starts_after_the_previous_one_completes() -> None:
    events = [
        buy(5 * MIN, 1, 1037),
        buy(8 * MIN, 1, 6333),
        buy(10 * MIN, 1, 1038),
        buy(14 * MIN, 1, 3031),
    ]
    points, _ = items_of(events)
    assert points == [DecisionPoint(1, 1, 5 * MIN, "6333"), DecisionPoint(1, 2, 10 * MIN, "3031")]


def test_buying_a_completed_item_outright_anchors_at_the_purchase() -> None:
    points, _ = items_of([buy(12 * MIN, 1, 3031)])
    assert points == [DecisionPoint(1, 1, 12 * MIN, "3031")]


def test_undone_purchases_are_ignored() -> None:
    events = [
        buy(5 * MIN, 1, 1038),
        undo(5 * MIN + 2_000, 1, 1038),
        buy(7 * MIN, 1, 1037),
        buy(9 * MIN, 1, 3071),
        undo(9 * MIN + 1_000, 1, 3071),
        buy(11 * MIN, 1, 6333),
    ]
    points, _ = items_of(events)
    assert points == [DecisionPoint(1, 1, 7 * MIN, "6333")]


def test_unfinished_slot_with_one_possible_item_is_inferred() -> None:
    events = [buy(5 * MIN, 1, 1037), buy(8 * MIN, 1, 6333), buy(20 * MIN, 1, 1038)]
    points, dropped = items_of(events)
    assert points[-1] == DecisionPoint(1, 2, 20 * MIN, "3031", inferred=True)
    assert not dropped


def test_unfinished_slot_with_several_possible_items_is_dropped_and_counted() -> None:
    points, dropped = items_of([buy(20 * MIN, 1, 3133)])
    assert points == []
    assert dropped == {"unfinished_slot": 1}


def test_slots_stop_at_the_maximum() -> None:
    events = [buy((5 + 2 * i) * MIN, 1, 3031) for i in range(MAX_SLOT + 2)]
    points, _ = items_of(events)
    assert [p.slot for p in points] == list(range(1, MAX_SLOT + 1))


def test_players_are_independent() -> None:
    events = [buy(5 * MIN, 2, 1038), buy(6 * MIN, 1, 1037), buy(9 * MIN, 2, 3031)]
    mine, _ = items_of(events, participant_id=1)
    theirs, _ = items_of(events, participant_id=2)
    assert theirs == [DecisionPoint(2, 1, 5 * MIN, "3031")]
    assert mine == []  # 1037 alone could become Death's Dance or Infinity Edge
