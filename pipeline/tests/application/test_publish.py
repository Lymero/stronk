import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from riot_builders import domain_match, domain_static

from stronk_contracts.build_v1 import Build
from stronk_contracts.manifest_v1 import Manifest
from stronk_pipeline.adapters import minisign
from stronk_pipeline.adapters.json_estimates import JsonEstimateStore
from stronk_pipeline.adapters.local_publisher import LocalPublisher
from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.minisign import MinisignKeys
from stronk_pipeline.application.publish import PublishParams, PublishResult, publish_command
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
ESTIMATES = [
    OptionEstimate("Champ1", "fighter", "TOP", 0, "8010", 0.012, (0.002, 0.022), 640, frozenset()),
    OptionEstimate(
        "Champ1", "fighter", "TOP", 1, "3071", None, None, 12, frozenset({Flag.LOW_OVERLAP})
    ),
    OptionEstimate("Champ1", "fighter", "TOP", 1, "6333", 0.03, (0.01, 0.05), 410, frozenset()),
]


def setup(tmp_path: Path, *, patches: tuple[str, ...] = ("16.20",)) -> Path:
    store = FileMatchStore(tmp_path / "crawl")
    store.put_static("16.20", domain_static())
    for i, patch in enumerate(patches):
        game = domain_match(f"EUW1_{i}")
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
