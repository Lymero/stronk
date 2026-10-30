from typing import Any

from board_sanity import check


def row(value: object, **rest: Any) -> dict[str, Any]:
    return {
        "value": value,
        "played": 10,
        "share": 0.5,
        "wpa": None,
        "ci": None,
        "versus": "alternatives",
        "confidence": "no_clear_difference",
        "fragile": False,
        "chosen": False,
        "listed": True,
        **rest,
    }


def plan(item_rows: list[dict[str, Any]], choice: int = 1) -> dict[str, Any]:
    empty: dict[str, Any] = {"rows": [], "more": 0}
    return {
        "runes": None,
        "spells": None,
        "items": [{"slot": 1, "value": choice, "label": "popular"}],
        "alternatives": {
            "runes": empty,
            "spells": empty,
            "start": empty,
            "components": empty,
            "boots": empty,
            "items": [{"slot": 1, "rows": item_rows, "more": 0}],
            "rune_rows": [],
        },
    }


def test_a_board_a_player_should_see_passes() -> None:
    good = [
        row(1, played=900, confidence="most_played", chosen=True),
        row(2, played=400, wpa=0.01, versus="most_played"),
        row(3, played=20, confidence="too_few_games"),
    ]
    failures, reported = check([("LeeSin/JUNGLE", plan(good))])
    assert (dict(failures), dict(reported)) == ({}, {})


def test_what_a_player_must_not_see_fails() -> None:
    bad = [
        row(1, played=4067, confidence="too_few_games", chosen=True),  # Triumph read "few games"
        row(2, played=1, confidence="almost_always"),  # a thin board read "almost always"
        row(3, wpa=0.02, confidence="clearly_better"),
    ]  # off the row's scale
    failures, _ = check([("LeeSin/JUNGLE", plan(bad, choice=2))])
    assert sorted(failures) == [
        "almost-always-few-games",
        "baseline-not-first",
        "choice-mismatch",
        "clear-off-scale",
        "few-games-false",
    ]


def test_a_number_against_another_option_is_reported_not_failed() -> None:
    rows = [row(1, played=900, confidence="most_played", chosen=True), row(2, played=400, wpa=0.01)]
    failures, reported = check([("Jinx/BOTTOM", plan(rows))])
    assert (dict(failures), list(reported)) == ({}, ["off-scale"])
