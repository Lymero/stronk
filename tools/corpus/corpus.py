"""The test corpus: larger real-data samples kept outside git, pinned in `corpus.lock` (ADR-015).

    corpus.py fetch [name...]                download, verify and unpack entries into corpus/
    corpus.py merge <out> <crawl...> [--games N]
                                             one crawl from several; N games stratified by crawl
    corpus.py pack <crawl> <name>            archive a crawl directory for publishing

Only `fetch` uses the network. An entry already unpacked with the same sha256 is not fetched
again. Archives hold the crawl's `matches/` and `static/`, never its `.salt`.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import sys
import tarfile
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import IO, cast, override

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "corpus.lock"
CORPUS = ROOT / "corpus"
PACKED = ("matches", "static")
MARKER = ".sha256"
GITHUB_ASSETS = "https://api.github.com/repos/"


@dataclass(frozen=True)
class Entry:
    name: str
    url: str
    sha256: str


class CorpusError(Exception):
    pass


def read_lock(path: Path = LOCK) -> list[Entry]:
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text())
    entries = data.get("file", [])
    if not isinstance(entries, list):
        raise CorpusError(f"{path}: `file` must be an array of tables")
    result: list[Entry] = []
    for raw in cast("list[object]", entries):
        match raw:
            case {"name": str(name), "url": str(url), "sha256": str(sha256)}:
                pass
            case _:
                raise CorpusError(f"{path}: every [[file]] needs name, url and sha256")
        if not name.replace("-", "").replace(".", "").replace("_", "").isalnum():
            raise CorpusError(f"{path}: unsafe corpus name {name!r}")
        result.append(Entry(name, url, sha256.lower()))
    return result


def select(entries: list[Entry], names: list[str]) -> list[Entry]:
    """The entries named, in lock order; all of them when no name is given."""
    known = {e.name for e in entries}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise CorpusError(f"not in corpus.lock: {', '.join(unknown)}")
    return [e for e in entries if not names or e.name in names]


def merge(crawls: list[Path], out: Path, games: int | None = None) -> dict[str, int]:
    """Copy several crawls' games and static data into one crawl directory at `out`.

    With `games`, a sample stratified by crawl (one crawl per region): each crawl contributes
    in proportion to its size, largest remainders first, and within a crawl the games with the
    smallest sha256 of their file name, so the choice is reproducible and ignores file order.
    Static data must agree where crawls share a patch. Returns games taken per crawl."""
    found = {c: sorted(p for p in (c / "matches").glob("*.json.gz")) for c in crawls}
    total = sum(len(f) for f in found.values())
    if total == 0:
        raise CorpusError("no games in " + ", ".join(map(str, crawls)))
    if games is not None and not 0 < games <= total:
        raise CorpusError(f"--games must be between 1 and {total}")
    take = {c: len(f) for c, f in found.items()} if games is None else _allocate(found, games)
    if (out / "matches").exists():
        raise CorpusError(f"{out} already holds matches; merge into a new directory")
    (out / "matches").mkdir(parents=True)
    (out / "static").mkdir()
    for crawl, files in found.items():
        for path in sorted(files, key=lambda p: hashlib.sha256(p.name.encode()).digest())[
            : take[crawl]
        ]:
            (out / "matches" / path.name).write_bytes(path.read_bytes())
        for path in sorted((crawl / "static").glob("*")):
            target = out / "static" / path.name
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise CorpusError(f"{path.name}: static data differs between crawls")
            target.write_bytes(path.read_bytes())
    return {c.name: take[c] for c in crawls}


def _allocate(found: dict[Path, list[Path]], games: int) -> dict[Path, int]:
    total = sum(len(f) for f in found.values())
    exact = {c: games * len(f) / total for c, f in found.items()}
    take = {c: int(v) for c, v in exact.items()}
    by_remainder = sorted(found, key=lambda c: (-(exact[c] - take[c]), str(c)))
    for c in by_remainder[: games - sum(take.values())]:
        take[c] += 1
    return take


def fetch(entries: list[Entry], corpus: Path = CORPUS) -> list[str]:
    """Bring corpus/ in line with the lock; returns what was done, one line per entry."""
    done: list[str] = []
    for entry in entries:
        target = corpus / entry.name
        marker = target / MARKER
        if marker.is_file() and marker.read_text().strip() == entry.sha256:
            done.append(f"{entry.name}: up to date")
            continue
        data = _download(entry.url)
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.sha256:
            raise CorpusError(f"{entry.name}: sha256 {digest} does not match the lock")
        _unpack(data, target)
        marker.write_text(entry.sha256 + "\n")
        done.append(f"{entry.name}: fetched {len(data) // 1024} KiB")
    return done


def pack(crawl: Path, out: Path) -> str:
    """Write a reproducible archive of `crawl` to `out`; returns its sha256."""
    buffer = io.BytesIO()
    # gzip's header holds a timestamp, the current second unless given: zero, like the members'.
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        files = sorted(p for d in PACKED for p in (crawl / d).rglob("*") if p.is_file())
        if not files:
            raise CorpusError(f"{crawl} has no {' or '.join(PACKED)} to pack")
        for path in files:
            info = tarfile.TarInfo(path.relative_to(crawl).as_posix())
            info.size = path.stat().st_size
            info.mtime = 0
            info.mode = 0o644
            with path.open("rb") as f:
                tar.addfile(info, f)
    data = buffer.getvalue()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _download(url: str) -> bytes:
    if url.startswith(GITHUB_ASSETS) and "/releases/assets/" in url:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise CorpusError("GitHub release assets need GITHUB_TOKEN (try `gh auth token`)")
        url = _asset_location(url, token)
    request = urllib.request.Request(url)  # noqa: S310 (URLs come from the reviewed lock)
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None  # surfaces the 302 as an HTTPError, Location intact


def _asset_location(url: str, token: str) -> str:
    """A private repo's release asset comes from the API, which answers with a redirect to
    signed storage. The token goes to api.github.com only, never to where it redirects."""
    request = urllib.request.Request(url)  # noqa: S310
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/octet-stream")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=60):
            pass
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
        if e.code in (301, 302, 303, 307, 308) and location.startswith("https://"):
            return location
        raise CorpusError(f"{url}: HTTP {e.code}") from e
    raise CorpusError(f"{url}: expected a redirect to the asset")


def _unpack(data: bytes, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(target, filter="data")  # rejects absolute paths and `..`


def main(argv: list[str]) -> int:
    try:
        match argv:
            case ["fetch", *names]:
                entries = select(read_lock(), names)
                if not entries:
                    print("corpus: corpus.lock lists no files yet")
                for line in fetch(entries):
                    print(f"corpus: {line}")
            case ["merge", out, *crawls] if crawls:
                games = None
                if len(crawls) >= 2 and crawls[-2] == "--games":
                    games, crawls = int(crawls[-1]), crawls[:-2]
                taken = merge([Path(c) for c in crawls], Path(out), games)
                print(f"merged into {out}: " + ", ".join(f"{k} {v}" for k, v in taken.items()))
            case ["pack", crawl, name]:
                out = ROOT / "dist" / "corpus" / f"{name}.tar.gz"
                digest = pack(Path(crawl), out)
                print(f'wrote {out}\n\n[[file]]\nname = {name!r}\nurl = "<upload URL>"')
                print(f'sha256 = "{digest}"')
            case _:
                print(__doc__)
                return 2
    except (CorpusError, OSError, ValueError, tarfile.TarError, tomllib.TOMLDecodeError) as e:
        print(f"corpus: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
