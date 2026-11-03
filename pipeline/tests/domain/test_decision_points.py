from collections import Counter
from dataclasses import replace

from riot_builders import Json, buy, domain_match, domain_static, kill, undo

from stronk_pipeline.domain.extract.decision_points import (
    BOOTS_SLOT,
    COMPONENTS_SLOT,
    LATE_SLOT,
    MAX_ITEMS,
    SKILL_LEVELS_SLOT,
    SKILL_MAX_SLOT,
    SPELLS_SLOT,
    START_SLOT,
    DecisionPoint,
    decision_points,
    first_components,
    is_rune_slot,
    is_tree,
    kept_purchases,
    skill_levels,
    skill_max,
    starting_items,
)
from stronk_pipeline.domain.extract.situation import damage_profile, enemy_magic_share
from stronk_pipeline.domain.match import ItemEvent, SkillEvent

STATIC = domain_static()
MIN = 60_000


def items_of(
    events: list[Json], participant_id: int = 1
) -> tuple[list[DecisionPoint], Counter[str]]:
    dropped: Counter[str] = Counter()
    points = decision_points(domain_match(events=events), STATIC, dropped)
    items = Counter({k: n for k, n in dropped.items() if not k.startswith("skill_")})
    return [
        p for p in points if p.participant_id == participant_id and 1 <= p.slot <= LATE_SLOT
    ], items


def test_every_player_has_a_keystone_decision_in_champion_select() -> None:
    points = decision_points(domain_match(), STATIC, Counter())
    keystones = [p for p in points if p.slot == 0]
    assert len(keystones) == 10
    assert keystones[0] == DecisionPoint(1, 0, 0, "8010")


def test_every_player_has_a_spells_decision_in_champion_select() -> None:
    """The pair is one option whichever key each spell is on (ADR-083), and no rune slot."""
    match = domain_match()
    swapped = replace(match.participants[1], spells=(14, 4))
    match = replace(match, participants=(match.participants[0], swapped, *match.participants[2:]))
    points = decision_points(match, STATIC, Counter())
    spells = [p for p in points if p.slot == SPELLS_SLOT]
    assert len(spells) == 10
    assert spells[0] == DecisionPoint(1, SPELLS_SLOT, 0, "4,14")
    assert spells[1] == DecisionPoint(2, SPELLS_SLOT, 0, "4,14")
    assert not is_rune_slot(SPELLS_SLOT)


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
    assert all(p.slot in (0, SPELLS_SLOT) or is_rune_slot(p.slot) for p in mine)
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


def test_items_from_the_fourth_share_the_late_slot_up_to_the_seventh() -> None:
    events = [buy((5 + 2 * i) * MIN, 1, 3031) for i in range(MAX_ITEMS + 2)]
    points, _ = items_of(events)
    assert [p.slot for p in points] == [1, 2, 3, LATE_SLOT, LATE_SLOT, LATE_SLOT, LATE_SLOT]
    assert [p.timestamp for p in points][3:] == [(5 + 2 * i) * MIN for i in range(3, MAX_ITEMS)]


def test_an_unfinished_late_item_takes_the_late_slot() -> None:
    events = [buy((5 + 2 * i) * MIN, 1, 3031) for i in range(5)] + [buy(20 * MIN, 1, 1038)]
    points, _ = items_of(events)
    assert points[-1] == DecisionPoint(1, LATE_SLOT, 20 * MIN, "3031", inferred=True)


def test_players_are_independent() -> None:
    events = [buy(5 * MIN, 2, 1038), buy(6 * MIN, 1, 1037), buy(9 * MIN, 2, 3031)]
    mine, _ = items_of(events, participant_id=1)
    theirs, _ = items_of(events, participant_id=2)
    assert theirs == [DecisionPoint(2, 1, 5 * MIN, "3031")]
    assert mine == []  # 1037 alone could become Death's Dance or Infinity Edge


def start_of(events: list[Json], participant_id: int = 1) -> list[DecisionPoint]:
    points = decision_points(domain_match(events=events), STATIC, Counter())
    return [p for p in points if p.participant_id == participant_id and p.slot == START_SLOT]


def test_the_start_is_its_items_without_supplies() -> None:
    # A trinket and potions come with Doran's Blade: the start is Doran's Blade.
    events = [buy(2_000, 1, 3340), buy(5_000, 1, 1055), buy(5_000, 1, 2003), buy(6_000, 1, 2003)]
    assert start_of(events) == [DecisionPoint(1, START_SLOT, 5_000, "1055")]
    assert not is_rune_slot(START_SLOT)


def test_a_start_of_several_items_is_one_option_and_keeps_what_was_bought() -> None:
    events = [buy(5_000, 1, 1055), buy(5_000, 1, 1036), buy(5_000, 1, 2003), buy(5_000, 1, 2003)]
    assert start_of(events) == [DecisionPoint(1, START_SLOT, 5_000, "1036,1055")]
    purchases = kept_purchases(domain_match(events=events).items, 1)
    assert starting_items(purchases, STATIC).bought == (1036, 1055, 2003, 2003)


def test_supplies_alone_and_undone_or_late_purchases_make_no_start() -> None:
    assert start_of([buy(5_000, 1, 2003), buy(5_000, 1, 3340)]) == []
    assert start_of([buy(5_000, 1, 1055), undo(7_000, 1, 1055)]) == []
    assert start_of([buy(2 * MIN, 1, 1055)]) == []


def test_unknown_items_count_in_the_start() -> None:
    late_patch_item = ItemEvent(timestamp=5_000, participant_id=1, action="purchased", item_id=9999)
    assert starting_items([late_patch_item], STATIC).option == "9999"


def components_of(events: list[Json], participant_id: int = 1) -> list[DecisionPoint]:
    points = decision_points(domain_match(events=events), STATIC, Counter())
    return [p for p in points if p.participant_id == participant_id and p.slot == COMPONENTS_SLOT]


def test_the_first_trip_back_buys_its_components_as_one_choice() -> None:
    # The start, then a Long Sword and a Pickaxe with a potion and boots on the first trip back:
    # the components without supplies or boots. A later purchase is another trip.
    events = [buy(5_000, 1, 1055), buy(4 * MIN, 1, 1036), buy(4 * MIN + 2_000, 1, 1037)]
    events += [buy(4 * MIN + 3_000, 1, 2003), buy(4 * MIN + 4_000, 1, 1001)]
    events += [buy(8 * MIN, 1, 1038)]
    assert components_of(events) == [DecisionPoint(1, COMPONENTS_SLOT, 4 * MIN, "1036,1037")]
    purchases = kept_purchases(domain_match(events=events).items, 1)
    assert first_components(purchases, STATIC, []).bought == (1001, 1036, 1037, 2003)


def test_a_trip_starts_at_its_first_component_and_skips_completed_items() -> None:
    # Potions and boots alone don't start the trip; a completed item doesn't count.
    events = [buy(3 * MIN, 1, 2003), buy(3 * MIN, 1, 1001), buy(6 * MIN, 1, 1037)]
    events += [buy(6 * MIN + 1_000, 1, 6333)]
    assert components_of(events) == [DecisionPoint(1, COMPONENTS_SLOT, 6 * MIN, "1037")]
    assert components_of([buy(3 * MIN, 1, 2003)]) == []


def boots_of(events: list[Json], participant_id: int = 1) -> list[DecisionPoint]:
    points = decision_points(domain_match(events=events), STATIC, Counter())
    return [p for p in points if p.participant_id == participant_id and p.slot == BOOTS_SLOT]


def test_boots_are_the_first_upgrade_anchored_at_the_plain_boots() -> None:
    events = [buy(5 * MIN, 1, 1001), buy(12 * MIN, 1, 3006)]
    assert boots_of(events) == [DecisionPoint(1, BOOTS_SLOT, 5 * MIN, "3006")]
    # Bought upgraded at once: anchored there. Never upgraded: no decision.
    assert boots_of([buy(9 * MIN, 1, 3006)]) == [DecisionPoint(1, BOOTS_SLOT, 9 * MIN, "3006")]
    assert boots_of([buy(5 * MIN, 1, 1001)]) == []


def test_a_first_back_after_a_death_isnt_measured_but_counted() -> None:
    # Player 1 dies at 3:00 (to player 6), then buys a Long Sword on respawn: not a planned back.
    events = [buy(5_000, 1, 1055), kill(3 * MIN, 6, 1), buy(3 * MIN + 20_000, 1, 1036)]
    points = decision_points(domain_match(events=events), STATIC, dropped := Counter())
    assert [p for p in points if p.participant_id == 1 and p.slot == COMPONENTS_SLOT] == []
    assert dropped["first_back_after_death"] == 1
    # A death after the first back changes nothing.
    events = [buy(4 * MIN, 1, 1036), kill(6 * MIN, 6, 1)]
    assert components_of(events) == [DecisionPoint(1, COMPONENTS_SLOT, 4 * MIN, "1036")]


def test_boots_are_also_measured_against_the_enemy_teams_damage() -> None:
    match = domain_match(events=[buy(5 * MIN, 1, 1001), buy(12 * MIN, 1, 3006)])
    profile = damage_profile(enemy_magic_share(match, 100, STATIC))
    points = [p for p in decision_points(match, STATIC, Counter()) if p.participant_id == 1]
    boots = [p for p in points if p.slot in range(BOOTS_SLOT, BOOTS_SLOT + 4)]
    assert boots == [
        DecisionPoint(1, BOOTS_SLOT, 5 * MIN, "3006"),
        DecisionPoint(1, BOOTS_SLOT + 1 + profile, 5 * MIN, "3006"),
    ]


def test_an_enemy_team_is_physical_mixed_or_magic_by_its_magic_share() -> None:
    assert [damage_profile(s) for s in (0.0, 0.42, 0.43, 0.49, 0.5, 1.0)] == [0, 0, 1, 1, 2, 2]


def ups(*slots: int) -> list[tuple[int, int]]:
    """Level-ups a minute apart, as (timestamp, skill slot)."""
    return [(i * MIN, s) for i, s in enumerate(slots)]


def test_the_first_levels_are_the_first_four_level_ups() -> None:
    assert skill_levels([1, 3, 2, 1, 1, 4]) == "1,3,2,1"
    assert skill_levels([1, 3, 2]) is None


def test_the_max_order_is_read_from_the_points_after_eleven_level_ups() -> None:
    # Q maxed at level 9, E ahead of W at level 11 (Q 5, E 3, W 1, R 2): anchored there.
    zed = ups(1, 2, 3, 1, 1, 4, 1, 3, 1, 3, 4, 3, 3, 2, 2, 4)
    assert skill_max(zed) == ("1,3,2", 10 * MIN)


def test_a_tie_is_settled_by_the_thirteenth_level_up_or_is_no_order() -> None:
    """Read later, the order would wait for late level-ups, which come with fights won."""
    # Zeri: Q and E even at 4 after eleven level-ups, E maxed at the twelfth.
    zeri = ups(3, 2, 1, 1, 4, 1, 3, 1, 3, 3, 4, 3, 2, 2, 2)
    assert skill_max(zeri) == ("3,1,2", 11 * MIN)
    assert skill_max(ups(1, 2, 3, 1, 1, 4, 1, 2, 1, 3, 4, 4, 1)) is None  # W 2, E 2 throughout
    assert skill_max(ups(1, 2, 3, 1, 1, 4, 1, 3, 1, 3)) is None  # a short game


def test_udyrs_r_is_a_basic_ability() -> None:
    udyr = ups(4, 1, 2, 4, 4, 4, 4, 3, 1, 1, 2)
    assert skill_max(udyr, r_is_basic=True) == ("4,1,2,3", 10 * MIN)


def with_skills(
    slots: list[int], participant_id: int = 1, champion_id: int | None = None
) -> tuple[list[DecisionPoint], Counter[str]]:
    match = domain_match()
    events = tuple(SkillEvent(i * MIN, participant_id, s) for i, s in enumerate(slots))
    match = replace(match, skills=events)
    if champion_id is not None:
        p = replace(match.participants[participant_id - 1], champion_id=champion_id)
        others = [q for q in match.participants if q.participant_id != participant_id]
        players = sorted([p, *others], key=lambda q: q.participant_id)
        match = replace(match, participants=tuple(players))
    dropped: Counter[str] = Counter()
    points = decision_points(match, STATIC, dropped)
    return [q for q in points if q.slot in (SKILL_LEVELS_SLOT, SKILL_MAX_SLOT)], dropped


def test_each_player_has_a_first_levels_and_a_max_order_decision() -> None:
    points, _ = with_skills([1, 2, 3, 1, 1, 4, 1, 3, 1, 3, 4, 3, 3, 2, 2])
    assert points == [
        DecisionPoint(1, SKILL_LEVELS_SLOT, 0, "1,2,3,1"),
        DecisionPoint(1, SKILL_MAX_SLOT, 10 * MIN, "1,3,2"),
    ]
    assert not is_rune_slot(SKILL_LEVELS_SLOT)
    assert not is_rune_slot(SKILL_MAX_SLOT)
    assert not is_tree(SKILL_LEVELS_SLOT // 10)


def test_an_evolving_champion_keeps_its_first_levels_only() -> None:
    """Kha'Zix's evolutions come as level-ups the stored games don't tell apart (ADR-085)."""
    points, _ = with_skills([1, 2, 3, 1, 1, 4, 1, 3, 1, 3, 4, 3, 3, 2, 2], champion_id=121)
    assert [p.slot for p in points] == [SKILL_LEVELS_SLOT]


def test_a_max_order_a_short_game_doesnt_show_is_dropped_and_counted() -> None:
    points, dropped = with_skills([1, 2, 3, 1, 2, 4])
    assert [p.slot for p in points] == [SKILL_LEVELS_SLOT]
    assert dropped["skill_max_short_game"] >= 1
