import json
from pathlib import Path

import pytest

from stronk_pipeline.adapters.local_publisher import LocalPublisher
from stronk_pipeline.domain.result import Err, Ok


def test_a_patch_is_replaced_as_a_whole(tmp_path: Path) -> None:
    publisher = LocalPublisher(tmp_path)
    publisher.publish("16.20", {"a/old.json": b"1", "manifest.json": b"m1"})
    result = publisher.publish("16.20", {"a/new.json": b"2", "manifest.json": b"m2"})
    assert isinstance(result, Ok)
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert files == ["16.20/a/new.json", "16.20/manifest.json", "index.json"]
    assert (tmp_path / "16.20" / "manifest.json").read_bytes() == b"m2"


def test_other_patches_are_untouched(tmp_path: Path) -> None:
    publisher = LocalPublisher(tmp_path)
    publisher.publish("16.19", {"manifest.json": b"old"})
    publisher.publish("16.20", {"manifest.json": b"new"})
    assert (tmp_path / "16.19" / "manifest.json").read_bytes() == b"old"


@pytest.mark.parametrize("path", ["../escape.json", "a/../../x", ".hidden", "a//b", "/abs", "a/.b"])
def test_unsafe_paths_are_refused(path: str, tmp_path: Path) -> None:
    result = LocalPublisher(tmp_path / "data").publish("16.20", {path: b"x"})
    assert isinstance(result, Err)
    assert not (tmp_path / "data").exists()


def test_odd_patch_is_refused(tmp_path: Path) -> None:
    assert isinstance(LocalPublisher(tmp_path).publish("../16.20", {"m.json": b""}), Err)


def test_the_index_lists_every_published_patch_oldest_first(tmp_path: Path) -> None:
    publisher = LocalPublisher(tmp_path)
    publisher.publish("16.20", {"manifest.json": b"b"})
    publisher.publish("16.3", {"manifest.json": b"a"})
    (tmp_path / "16.21").mkdir()  # no manifest: not a patch
    result = publisher.publish("17.1", {"manifest.json": b"c"})
    assert isinstance(result, Ok)
    assert str(tmp_path / "index.json") in result.value
    index = (tmp_path / "index.json").read_text()
    assert json.loads(index) == {"schemaVersion": 1, "patches": ["16.3", "16.20", "17.1"]}
    assert index.endswith("\n")
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == []
