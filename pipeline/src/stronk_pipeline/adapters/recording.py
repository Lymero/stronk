"""Record HTTP responses during a live crawl and play them back in tests (no network).

A recording is a directory of `<key>.json.gz` files, one per request, holding the URL, status
and JSON body. The key hashes the host, path and query, never headers, so the API key is never
part of a recording.

Recordings are made to be committed, so they are scrubbed as they are written: Riot ids and
names are removed and every PUUID, in bodies and in URLs, becomes a pseudonym of the same
shape. Pseudonyms are consistent within one recording, so playback can still walk from a
league to a player's games.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import cast

import httpx

PUUID = re.compile(r"[A-Za-z0-9_-]{78}")
IDENTITY_KEYS = frozenset(
    {"riotIdGameName", "riotIdTagline", "riotIdName", "summonerName", "summonerId", "gameName"}
)
RECORDED_STATUSES = frozenset({200, 404})


def recording_key(url: httpx.URL) -> str:
    query = "&".join(sorted(f"{k}={v}" for k, v in url.params.multi_items()))
    identity = f"{url.host}{url.path}?{query}"
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


class Scrubber:
    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt if salt is not None else secrets.token_bytes(32)

    def pseudonym(self, puuid: str) -> str:
        digest = hmac.new(self._salt, puuid.encode(), hashlib.sha512).digest()
        return base64.urlsafe_b64encode(digest).decode()[:78]

    def url(self, url: httpx.URL) -> httpx.URL:
        path = "/".join(
            self.pseudonym(part) if PUUID.fullmatch(part) else part for part in url.path.split("/")
        )
        return url.copy_with(path=path)

    def body(self, value: object) -> object:
        """`value` (parsed JSON) without identities."""
        if isinstance(value, dict):
            items = cast("dict[str, object]", value).items()
            return {k: self.body(v) for k, v in items if k not in IDENTITY_KEYS}
        if isinstance(value, list):
            return [self.body(v) for v in cast("list[object]", value)]
        if isinstance(value, str) and PUUID.fullmatch(value):
            return self.pseudonym(value)
        return value


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes requests through and saves a scrubbed copy of each JSON response."""

    def __init__(
        self, inner: httpx.AsyncBaseTransport, directory: Path, scrubber: Scrubber
    ) -> None:
        self._inner = inner
        self._directory = directory
        self._scrubber = scrubber

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        content = await response.aread()
        if response.status_code in RECORDED_STATUSES:
            try:
                body = json.loads(content)
            except ValueError:
                return response
            url = self._scrubber.url(request.url)
            record = {
                "url": str(url),
                "status": response.status_code,
                "body": self._scrubber.body(body),
            }
            _write(self._directory / f"{recording_key(url)}.json.gz", record)
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


class PlaybackTransport(httpx.AsyncBaseTransport):
    """Answers from a recording; anything not recorded is a 404."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = self._directory / f"{recording_key(request.url)}.json.gz"
        try:
            record = json.loads(gzip.decompress(path.read_bytes()))
            status = int(record["status"])
            body = record["body"]
        except (OSError, ValueError, KeyError, TypeError):
            return httpx.Response(404, json={"status": {"message": "not recorded"}})
        return httpx.Response(status, json=body)


def _write(path: Path, record: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(record, separators=(",", ":")).encode(), mtime=0))
    tmp.replace(path)
