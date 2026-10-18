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
    assert files == ["16.20/a/new.json", "16.20/manifest.json"]
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
