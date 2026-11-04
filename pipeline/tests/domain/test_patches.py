from dataclasses import replace

import pytest
from riot_builders import domain_static

from stronk_pipeline.domain.patches import (
    MissingFingerprintsError,
    changed_in,
    changed_items,
    changed_since,
    in_order,
)
from stronk_pipeline.domain.static import StaticData

STATIC = domain_static()


def changing(static: StaticData, *items: int, to: str = "changed") -> StaticData:
    return replace(
        static,
        items={**static.items, **{i: replace(static.items[i], fingerprint=to) for i in items}},
    )


def test_patches_sort_as_numbers_each_once() -> None:
    assert in_order(["16.10", "16.9", "16.10", "15.24"]) == ["15.24", "16.9", "16.10"]


def test_an_item_changed_when_its_fingerprint_differs() -> None:
    assert changed_items(STATIC, STATIC) == frozenset()
    assert changed_items(STATIC, changing(STATIC, 6333)) == {6333}


def test_game_data_without_fingerprints_cannot_tell_changes() -> None:
    blank = replace(
        STATIC, items={i: replace(it, fingerprint="") for i, it in STATIC.items.items()}
    )
    with pytest.raises(MissingFingerprintsError, match="no item fingerprints"):
        changed_items(blank, STATIC)


def test_each_older_patch_against_the_newest() -> None:
    # 6333 changed in 16.20 and back in 16.21: the same as on 16.19, so unchanged since.
    statics = {
        "16.19": STATIC,
        "16.20": changing(STATIC, 6333, 1037),
        "16.21": changing(STATIC, 1037),
    }
    assert changed_since(statics, ["16.21", "16.19", "16.20"]) == {
        "16.19": {1037},
        "16.20": {6333},
    }
    assert changed_since({"16.20": STATIC}, ["16.20"]) == {}


def test_an_item_is_published_with_the_latest_patch_that_changed_it() -> None:
    statics = {
        "16.19": STATIC,
        "16.20": changing(STATIC, 6333, 1037),
        "16.21": changing(STATIC, 6333, 1037, to="again"),
    }
    assert changed_in(statics, statics) == {6333: "16.21", 1037: "16.21"}
    assert changed_in({k: statics[k] for k in ("16.19", "16.20")}, ["16.19", "16.20"]) == {
        6333: "16.20",
        1037: "16.20",
    }
