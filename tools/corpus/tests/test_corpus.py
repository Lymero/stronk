import email.message
import hashlib
import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from corpus import CorpusError, Entry, fetch, merge, pack, read_lock, select


def crawl_dir(root: Path) -> Path:
    (root / "matches").mkdir(parents=True)
    (root / "static").mkdir()
    (root / "matches" / "EUW1_1.json.gz").write_bytes(b"game")
    (root / "static" / "16.20.json.gz").write_bytes(b"static")
    (root / ".salt").write_text("secret")
    return root


def packed(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "out" / "c.tar.gz"
    return archive, pack(crawl_dir(tmp_path / "crawl"), archive)


def test_pack_is_reproducible_and_leaves_out_the_salt(tmp_path: Path) -> None:
    archive, digest = packed(tmp_path)
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    again = pack(tmp_path / "crawl", tmp_path / "again.tar.gz")
    assert again == digest
    corpus = tmp_path / "corpus"
    fetch([Entry("c", archive.as_uri(), digest)], corpus)
    assert (corpus / "c" / "matches" / "EUW1_1.json.gz").read_bytes() == b"game"
    assert not (corpus / "c" / ".salt").exists()


def test_fetch_skips_what_is_up_to_date(tmp_path: Path) -> None:
    archive, digest = packed(tmp_path)
    entry = Entry("c", archive.as_uri(), digest)
    fetch([entry], tmp_path / "corpus")
    archive.unlink()  # would fail if fetched again
    assert fetch([entry], tmp_path / "corpus") == ["c: up to date"]


def test_fetch_rejects_a_wrong_hash(tmp_path: Path) -> None:
    archive, _ = packed(tmp_path)
    with pytest.raises(CorpusError, match="does not match"):
        fetch([Entry("c", archive.as_uri(), "0" * 64)], tmp_path / "corpus")
    assert not (tmp_path / "corpus" / "c").exists()


def test_read_lock(tmp_path: Path) -> None:
    lock = tmp_path / "corpus.lock"
    lock.write_text('[[file]]\nname = "crawl-euw1"\nurl = "https://x/y.tar.gz"\nsha256 = "AB"\n')
    assert read_lock(lock) == [Entry("crawl-euw1", "https://x/y.tar.gz", "ab")]
    assert read_lock(tmp_path / "missing.lock") == []


@pytest.mark.parametrize(
    "body",
    ['[[file]]\nname = "../x"\nurl = "u"\nsha256 = "s"\n', '[[file]]\nname = "x"\n', "file = 1\n"],
)
def test_read_lock_rejects_bad_entries(tmp_path: Path, body: str) -> None:
    lock = tmp_path / "corpus.lock"
    lock.write_text(body)
    with pytest.raises(CorpusError):
        read_lock(lock)


ASSET = "https://api.github.com/repos/o/r/releases/assets/1"


def test_release_asset_needs_a_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(CorpusError, match="GITHUB_TOKEN"):
        fetch([Entry("c", ASSET, "0" * 64)], tmp_path / "corpus")


def test_token_goes_to_the_api_but_not_to_the_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, digest = packed(tmp_path)
    storage = "https://storage.example/signed?sig=1"
    seen: list[urllib.request.Request] = []

    class Opener:
        def open(self, request: urllib.request.Request, timeout: float) -> None:
            seen.append(request)
            headers = email.message.Message()
            headers["Location"] = storage
            raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, None)

    def urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        seen.append(request)
        return io.BytesIO(archive.read_bytes())

    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")

    def build_opener(*_: object) -> Opener:
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    fetch([Entry("c", ASSET, digest)], tmp_path / "corpus")
    api, signed = seen
    assert api.full_url == ASSET
    assert api.get_header("Authorization") == "Bearer t0ken"
    assert api.get_header("Accept") == "application/octet-stream"
    assert signed.full_url == storage
    assert not signed.has_header("Authorization")
    assert (tmp_path / "corpus" / "c" / "matches" / "EUW1_1.json.gz").is_file()


def region(root: Path, prefix: str, n: int) -> Path:
    (root / "matches").mkdir(parents=True)
    (root / "static").mkdir()
    for i in range(n):
        (root / "matches" / f"{prefix}_{i}.json.gz").write_bytes(f"{prefix}{i}".encode())
    (root / "static" / "16.20.json.gz").write_bytes(b"static")
    return root


def games_in(crawl: Path) -> list[str]:
    return sorted(p.name for p in (crawl / "matches").iterdir())


def test_merge_takes_every_game_without_a_count(tmp_path: Path) -> None:
    crawls = [region(tmp_path / "euw1", "EUW1", 3), region(tmp_path / "kr", "KR", 2)]
    assert merge(crawls, tmp_path / "all") == {"euw1": 3, "kr": 2}
    assert len(list((tmp_path / "all" / "matches").iterdir())) == 5
    assert (tmp_path / "all" / "static" / "16.20.json.gz").read_bytes() == b"static"


def test_merge_stratifies_by_crawl_reproducibly(tmp_path: Path) -> None:
    crawls = [region(tmp_path / "euw1", "EUW1", 80), region(tmp_path / "kr", "KR", 70),
              region(tmp_path / "na1", "NA1", 50)]  # fmt: skip
    taken = merge(crawls, tmp_path / "a", games=21)
    assert taken == {
        "euw1": 9,
        "kr": 7,
        "na1": 5,
    }  # 8.4, 7.35, 5.25: one more to the largest remainder
    again = merge(list(reversed(crawls)), tmp_path / "b", games=21)
    assert sorted(again.items()) == sorted(taken.items())
    assert games_in(tmp_path / "a") == games_in(tmp_path / "b")


def test_merge_refuses_disagreeing_static_data(tmp_path: Path) -> None:
    a, b = region(tmp_path / "a", "EUW1", 1), region(tmp_path / "b", "KR", 1)
    (b / "static" / "16.20.json.gz").write_bytes(b"other")
    with pytest.raises(CorpusError, match="static data differs"):
        merge([a, b], tmp_path / "out")


def test_select_fetches_only_the_named_entries() -> None:
    entries = [Entry("ci", "u1", "a"), Entry("full", "u2", "b")]
    assert select(entries, []) == entries
    assert select(entries, ["ci"]) == [entries[0]]
    with pytest.raises(CorpusError, match=r"not in corpus\.lock"):
        select(entries, ["nope"])
