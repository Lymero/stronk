from pathlib import Path

from riot_builders import domain_match, domain_static

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.domain.result import Err, Ok


def test_round_trip(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    game = domain_match("EUW1_7")
    assert store.put(game) == Ok(None)
    assert store.put_static("16.20", domain_static()) == Ok(None)
    assert store.count() == 1
    assert store.read_matches() == Ok(([game], 0))
    statics = store.read_static()
    assert isinstance(statics, Ok)
    assert statics.value["16.20"].completed_items == domain_static().completed_items
    assert store.has_static("16.20")
    assert not store.has_static("16.19")


def test_known_includes_stored_and_skipped(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    store.put(domain_match("EUW1_1"))
    store.skip("EUW1_2", "remake")
    assert store.known() == Ok(frozenset({"EUW1_1", "EUW1_2"}))
    assert store.count() == 1


def test_a_cut_off_skip_line_is_ignored(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    store.skip("EUW1_2", "remake")
    with (tmp_path / "skipped.jsonl").open("a") as f:
        f.write('{"id": "EUW1_3", "rea')
    assert store.known() == Ok(frozenset({"EUW1_2"}))


def test_unreadable_files_are_counted_not_fatal(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    store.put(domain_match("EUW1_1"))
    (tmp_path / "matches" / "EUW1_2.json.gz").write_bytes(b"not gzip")
    result = store.read_matches()
    assert isinstance(result, Ok)
    assert len(result.value[0]) == 1
    assert result.value[1] == 1


def test_salt_is_created_once(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path / "crawl")
    first = store.salt()
    assert isinstance(first, Ok)
    assert len(first.value) == 32
    assert FileMatchStore(tmp_path / "crawl").salt() == first


def test_empty_store_writes_nothing(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path / "crawl")
    assert store.known() == Ok(frozenset[str]())
    assert store.count() == 0
    assert not (tmp_path / "crawl").exists()


def test_missing_directory_is_not_found(tmp_path: Path) -> None:
    result = FileMatchStore(tmp_path / "nope").read_matches()
    assert isinstance(result, Err)
    assert result.error.kind == "not_found"


def test_unexpected_ids_are_refused(tmp_path: Path) -> None:
    result = FileMatchStore(tmp_path).put(domain_match("../escape"))
    assert isinstance(result, Err)
    assert not list(tmp_path.parent.glob("escape*"))
