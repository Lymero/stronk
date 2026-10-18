from dataclasses import replace

from riot_builders import domain_match, domain_static

from stronk_pipeline.domain.publish import RunePage, played

PAGE = RunePage(8100, 8300, (8010, 8139, 8138, 8135, 8345, 8347, 5008, 5008, 5011))


def test_counts_games_and_keeps_each_keystones_page() -> None:
    result = played([domain_match("EUW1_1"), domain_match("EUW1_2")], {"16.20": domain_static()})
    assert result.games[("Champ1", "TOP")] == 2
    assert result.pages[("Champ1", "TOP", 8010)] == (PAGE, 2)


def test_most_played_page_wins_and_ties_never_depend_on_order() -> None:
    games = [domain_match(f"EUW1_{i}") for i in range(3)]
    p = games[0].participants[0]
    other = replace(p, stat_perks=(5005, 5008, 5011))
    games[0] = replace(games[0], participants=(other, *games[0].participants[1:]))
    statics = {"16.20": domain_static()}
    assert played(games, statics).pages[("Champ1", "TOP", 8010)] == (PAGE, 2)  # 2 against 1
    tie = played(games[:2], statics).pages[("Champ1", "TOP", 8010)]
    assert tie == played(games[1::-1], statics).pages[("Champ1", "TOP", 8010)]


def test_games_without_static_data_are_left_out() -> None:
    result = played([domain_match("EUW1_1")], {})
    assert not result.games
    assert not result.pages


def test_spell_pairs_count_whichever_key_each_spell_is_on() -> None:
    games = [domain_match(f"EUW1_{i}") for i in range(3)]
    p = games[0].participants[0]
    swapped = replace(p, spells=(p.spells[1], p.spells[0]))
    games[0] = replace(games[0], participants=(swapped, *games[0].participants[1:]))
    pairs = played(games, {"16.20": domain_static()}).spells[("Champ1", "TOP")]
    assert pairs == [(p.spells, 3)]  # one pair, in its usual order (2 of 3 games)
