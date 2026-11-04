from dataclasses import replace

import numpy as np
from riot_builders import buy, domain_match, domain_static

from stronk_pipeline.domain.extract.tables import DECISION_FEATURES, extract
from stronk_pipeline.domain.match import Match

MIN = 60_000
STATIC = domain_static()


def matches() -> list[Match]:
    events = [buy(5 * MIN, 1, 1037), buy(8 * MIN, 1, 6333), buy(6 * MIN, 7, 1038)]
    return [
        domain_match("EUW1_1", events=events, minutes=25, gold={1: 80}),
        domain_match("EUW1_2", created=1_760_100_000_000, winner=200, minutes=20),
    ]


def test_frames_have_both_teams_for_every_minute_but_the_first() -> None:
    frames = extract(matches(), {"16.20": STATIC}).frames
    assert len(frames) == 2 * (25 + 20)
    first = frames.match_id == "EUW1_1"
    assert set(frames.team[first]) == {100, 200}
    assert frames.outcome[first & (frames.team == 100)].all()
    assert frames.minute.min() > 0


def test_decisions_have_keystones_and_item_slots() -> None:
    extracted = extract(matches(), {"16.20": STATIC})
    decisions = extracted.decisions
    assert decisions.feature_names == DECISION_FEATURES
    assert (decisions.slot == 0).sum() == 20
    items = (decisions.slot > 0) & (decisions.slot <= 6)
    assert sorted(decisions.option[items].tolist()) == ["3031", "6333"]
    runes = dict.fromkeys((81001, 81002, 81003, 83005, 50001, 50002, 50003), 20)
    # Two players start an item after the start: their first components (ADR-072).
    assert extracted.stats.decisions_by_slot == {0: 20, 1: 2, 60001: 2, 70000: 20, **runes}
    assert extracted.stats.inferred == 1  # participant 7 never finished Infinity Edge
    row = np.flatnonzero(decisions.option == "6333")[0]
    assert decisions.champion[row] == "Champ1"
    assert decisions.champion_class[row] == "fighter"
    assert decisions.role[row] == "TOP"
    assert decisions.minute[row] == 5.0
    assert decisions.outcome[row] == 1


def test_matches_without_static_data_or_with_unknown_champions_are_dropped() -> None:
    unknown = domain_match("EUW1_3", champions=[1, 2, 3, 4, 5, 6, 7, 8, 9, 999])
    old_patch = replace(domain_match("EUW1_4"), patch="16.19")
    extracted = extract([*matches(), unknown, old_patch], {"16.20": STATIC})
    assert extracted.stats.matches == 2
    # The builder's games have no level-ups, so no max order either (ADR-085).
    assert extracted.stats.dropped == {
        "unknown_champion": 1,
        "no_static_data": 1,
        "skill_max_short_game": 20,
    }


def test_input_order_does_not_change_the_tables() -> None:
    forward = extract(matches(), {"16.20": STATIC}).decisions
    backward = extract(list(reversed(matches())), {"16.20": STATIC}).decisions
    np.testing.assert_array_equal(forward.option, backward.option)
    np.testing.assert_array_equal(forward.features, backward.features)


def test_no_matches_gives_empty_tables() -> None:
    extracted = extract([], {"16.20": STATIC})
    assert len(extracted.frames) == 0
    assert len(extracted.decisions) == 0


def test_older_patch_choices_of_changed_items_are_left_out() -> None:
    # Regression guard for pooling (ADR-088): Pickaxe (1037) and 6333 changed in 16.20, so a
    # 16.19 game's choices of them don't count; the rest of that game does.
    new = replace(matches()[0], match_id="EUW1_3")
    old = replace(matches()[0], patch="16.19")
    statics = {"16.19": STATIC, "16.20": STATIC}
    extracted = extract([old, new], statics, changed={"16.19": frozenset({1037, 6333})})
    d = extracted.decisions
    bought = (d.slot >= 1) & ((d.slot <= 4) | (d.slot >= 60_000)) & (d.slot < 70_000)
    options = {
        m: sorted(d.option[bought & (d.match_id == m)].tolist()) for m in ("EUW1_1", "EUW1_3")
    }
    assert options == {"EUW1_1": ["1038", "3031"], "EUW1_3": ["1037", "1038", "3031", "6333"]}
    assert extracted.stats.dropped["changed_item_older_patch"] == 2
    keystones = d.slot == 0
    assert (d.match_id[keystones] == "EUW1_1").sum() == (d.match_id[keystones] == "EUW1_3").sum()
