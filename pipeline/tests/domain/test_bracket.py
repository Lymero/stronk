from stronk_pipeline.domain.bracket import BRACKETS, bracket_of, ordered, published


def test_tiers_make_one_band_each() -> None:
    assert bracket_of(["CHALLENGER", "GRANDMASTER", "MASTER"]) == "master_plus"
    assert bracket_of(["DIAMOND"]) == "diamond"
    assert bracket_of(["EMERALD"]) == "emerald"
    assert bracket_of(["MASTER", "DIAMOND"]) is None
    assert bracket_of([]) is None


def test_a_bracket_is_a_band_with_every_band_above_it() -> None:
    assert published(["master_plus"]) == "master_plus"
    assert published(["diamond", "master_plus", "diamond"]) == "diamond_plus"
    assert published(["emerald", "diamond", "master_plus"]) == "emerald_plus"
    # A band missing above another: no bracket.
    assert published(["diamond"]) is None
    assert published(["master_plus", "emerald"]) is None
    assert published([]) is None
    assert list(BRACKETS) == ["master_plus", "diamond_plus", "emerald_plus"]


def test_bands_come_highest_first_once() -> None:
    assert ordered(["emerald", "master_plus", "emerald", "diamond"]) == [
        "master_plus",
        "diamond",
        "emerald",
    ]
