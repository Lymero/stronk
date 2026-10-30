import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from riot_builders import buy, domain_match, domain_static

from stronk_contracts.build_v1 import Build
from stronk_contracts.manifest_v1 import Manifest
from stronk_pipeline.adapters import minisign
from stronk_pipeline.adapters.json_estimates import JsonEstimateStore
from stronk_pipeline.adapters.local_publisher import LocalPublisher
from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.minisign import MinisignKeys
from stronk_pipeline.application.publish import PublishParams, PublishResult, publish_command
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.domain.extract.decision_points import START_SLOT
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
ESTIMATES = [
    OptionEstimate("Champ1", "fighter", "TOP", 0, "8010", 0.012, (0.002, 0.022), 640, frozenset()),
    OptionEstimate(
        "Champ1", "fighter", "TOP", 1, "3071", None, None, 12, frozenset({Flag.LOW_OVERLAP})
    ),
    OptionEstimate("Champ1", "fighter", "TOP", 1, "6333", 0.03, (0.01, 0.05), 410, frozenset()),
    # The rest of the page, row by row (ADR-057): a primary row, a secondary pair, a shard row.
    OptionEstimate(
        "Champ1",
        "fighter",
        "TOP",
        81001,
        "9111",
        0.004,
        (-0.01, 0.02),
        500,
        frozenset(),
        chosen=500,
    ),
    OptionEstimate(
        "Champ1",
        "fighter",
        "TOP",
        81001,
        "8009",
        -0.01,
        (-0.03, 0.01),
        200,
        frozenset({Flag.NO_CLEAR_DIFFERENCE}),
        q=0.8,
        versus="9111",
        contrast=-0.012,
        contrast_ci=(-0.04, 0.016),
        chosen=200,
    ),
    OptionEstimate(
        "Champ1", "fighter", "TOP", 83005, "8135,8143", 0.002, (-0.01, 0.014), 300, chosen=300
    ),
    OptionEstimate("Champ1", "fighter", "TOP", 50002, "5008", None, None, 12, chosen=12),
    # Starts (ADR-071): Doran's Blade, and a Long Sword start compared with it.
    OptionEstimate(
        "Champ1", "fighter", "TOP", START_SLOT, "1055", 0.001, (-0.01, 0.012), 700, chosen=700
    ),
    OptionEstimate(
        "Champ1",
        "fighter",
        "TOP",
        START_SLOT,
        "1036",
        -0.004,
        (-0.02, 0.012),
        320,
        frozenset({Flag.NO_CLEAR_DIFFERENCE}),
        q=0.7,
        versus="1055",
        contrast=-0.005,
        contrast_ci=(-0.03, 0.02),
        chosen=320,
    ),
]


def setup(tmp_path: Path, *, patches: tuple[str, ...] = ("16.20",)) -> Path:
    store = FileMatchStore(tmp_path / "crawl")
    store.put_static("16.20", domain_static())
    for i, patch in enumerate(patches):
        # Champ1 starts Doran's Blade with two potions and a trinket.
        start = [buy(2_000, 1, 3340), buy(4_000, 1, 1055), buy(4_000, 1, 2003), buy(4_000, 1, 2003)]
        game = domain_match(f"EUW1_{i}", events=start)
        store.put(replace(game, patch=patch))
    JsonEstimateStore().write_estimates("v1-reference", ESTIMATES, tmp_path / "estimates.json")
    MinisignKeys().generate(tmp_path / "k.key")
    return tmp_path


def publish(tmp_path: Path, **params: object) -> Result[PublishResult, CommandError]:
    command = publish_command(
        JsonEstimateStore(), FileMatchStore, MinisignKeys(), LocalPublisher, clock=lambda: NOW
    )
    defaults = {
        "estimates": str(tmp_path / "estimates.json"),
        "crawl": str(tmp_path / "crawl"),
        "key": str(tmp_path / "k.key"),
        "out": str(tmp_path / "dist"),
    }
    return command.run(PublishParams.model_validate({**defaults, **params}))


def test_publishes_each_rune_row_for_information(tmp_path: Path) -> None:
    assert isinstance(publish(setup(tmp_path)), Ok)
    path = tmp_path / "dist" / "16.20" / "all" / "master_plus" / "Champ1" / "TOP.json"
    choices = json.loads(path.read_text())["runeChoices"]
    assert choices == [
        {
            "kind": "shard",
            "row": 2,
            "perks": [5008],
            "games": 12,
            "wpa": None,
            "ci": None,
            "n": 12,
            "flags": [],
        },
        {
            "kind": "primary",
            "style": 8100,
            "row": 1,
            "perks": [9111],
            "games": 500,
            "wpa": 0.004,
            "ci": [-0.01, 0.02],
            "n": 500,
            "flags": [],
        },
        {
            "kind": "primary",
            "style": 8100,
            "row": 1,
            "perks": [8009],
            "games": 200,
            "wpa": -0.01,
            "ci": [-0.03, 0.01],
            "n": 200,
            "flags": ["no_clear_difference"],
            "comparison": {"versus": [9111], "wpa": -0.012, "q": 0.8, "ci": [-0.04, 0.016]},
        },
        {
            "kind": "secondary",
            "style": 8300,
            "perks": [8135, 8143],
            "games": 300,
            "wpa": 0.002,
            "ci": [-0.01, 0.014],
            "n": 300,
            "flags": [],
        },
    ]


def test_publishes_starts_with_what_is_bought_with_them(tmp_path: Path) -> None:
    assert isinstance(publish(setup(tmp_path)), Ok)
    path = tmp_path / "dist" / "16.20" / "all" / "master_plus" / "Champ1" / "TOP.json"
    assert json.loads(path.read_text())["starts"] == [
        {
            "items": [1055],
            "buy": [1055, 2003, 2003, 3340],
            "games": 700,
            "wpa": 0.001,
            "ci": [-0.01, 0.012],
            "n": 700,
            "flags": [],
        },
        {
            "items": [1036],
            "buy": [1036],  # never seen in these games: its items alone
            "games": 320,
            "wpa": -0.004,
            "ci": [-0.02, 0.012],
            "n": 320,
            "flags": ["no_clear_difference"],
            "comparison": {"versus": [1055], "wpa": -0.005, "q": 0.7, "ci": [-0.03, 0.02]},
        },
    ]


def test_publishes_signed_valid_builds(tmp_path: Path) -> None:
    result = publish(setup(tmp_path))
    assert isinstance(result, Ok)
    root = tmp_path / "dist" / "16.20"
    manifest_bytes = (root / "manifest.json").read_bytes()
    public = (tmp_path / "k.key.pub").read_text()
    comment = minisign.verify(public, manifest_bytes, (root / "manifest.json.minisig").read_bytes())
    assert comment == Ok(f"stronk manifest v1 patch=16.20 runId={result.value.run_id}")
    manifest = Manifest.model_validate_json(manifest_bytes)
    assert manifest.key_id == result.value.key_id
    assert manifest.run_id.startswith("20261018T120000Z-")
    assert [f.path for f in manifest.files] == ["all/master_plus/Champ1/TOP.json"]
    data = (root / manifest.files[0].path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest.files[0].sha256
    assert len(data) == manifest.files[0].bytes
    build = Build.model_validate_json(data)
    assert build.games == 1
    assert build.runes[0].page.perks[0].root == 8010
    assert [(i.item, i.wpa) for i in build.items] == [(6333, 0.03), (3071, None)]
    assert "skillOrder" not in json.loads(data)


def test_same_inputs_give_the_same_files(tmp_path: Path) -> None:
    setup(tmp_path)
    first = publish(tmp_path)
    second = publish(tmp_path)
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert first.value.run_id == second.value.run_id


def test_crawls_of_two_patches_are_refused(tmp_path: Path) -> None:
    result = publish(setup(tmp_path, patches=("16.20", "16.19")))
    assert isinstance(result, Err)
    assert "one patch" in result.error.message


def test_missing_key_is_not_found_and_nothing_is_published(tmp_path: Path) -> None:
    setup(tmp_path)
    result = publish(tmp_path, key=str(tmp_path / "nope.key"))
    assert isinstance(result, Err)
    assert result.error.code == "not_found"
    assert not (tmp_path / "dist").exists()
