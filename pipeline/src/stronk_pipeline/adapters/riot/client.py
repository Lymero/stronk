"""MatchSource over the Riot API (league-v4, match-v5) and Data Dragon.

The HTTP transport is injected: live, live with recording, or playback of a recording
(`adapters/recording.py`), so tests run this exact code without the network.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping

import httpx
from pydantic import TypeAdapter, ValidationError

from stronk_pipeline.adapters.riot.payloads import (
    ChampionsPayload,
    ItemsPayload,
    League,
    LeagueEntry,
    MatchPayload,
    PayloadError,
    TimelinePayload,
    to_match,
    to_static,
)
from stronk_pipeline.adapters.riot.rate_limit import RateLimiter
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import MatchHeader, Platform, Skipped, SourceError, SourceStats, Tier

log = logging.getLogger(__name__)

REGIONS: Mapping[str, str] = {
    "br1": "americas", "la1": "americas", "la2": "americas", "na1": "americas",
    "eun1": "europe", "euw1": "europe", "me1": "europe", "ru": "europe", "tr1": "europe",
    "jp1": "asia", "kr": "asia",
    "oc1": "sea", "sg2": "sea", "tw2": "sea", "vn2": "sea",
}  # fmt: skip
"""match-v5 is served per region, league-v4 per platform."""
DATA_DRAGON = "https://ddragon.leagueoflegends.com"
RANKED_SOLO = 420
MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 60.0

_MATCH_IDS = TypeAdapter(list[str])
_VERSIONS = TypeAdapter(list[str])
_ENTRIES = TypeAdapter(list[LeagueEntry])
_LEAGUE = TypeAdapter(League)
_MATCH = TypeAdapter(MatchPayload)
_TIMELINE = TypeAdapter(TimelinePayload)
_CHAMPIONS = TypeAdapter(ChampionsPayload)
_ITEMS = TypeAdapter(ItemsPayload)


class RiotApiSource:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        platform: Platform,
        api_key: str,
        limiter: RateLimiter | None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._platform = f"https://{platform}.api.riotgames.com"
        self._region = f"https://{REGIONS[platform]}.api.riotgames.com"
        self._headers = {"X-Riot-Token": api_key}
        self._limiter = limiter
        self._clock = clock
        self._sleep = sleep
        self._requests = 0
        self._retries = 0
        self._waited = 0.0

    async def players(self, tier: Tier) -> Result[list[str], SourceError]:
        if tier == "DIAMOND":
            url = f"{self._platform}/lol/league/v4/entries/RANKED_SOLO_5x5/DIAMOND/I"
            body = await self._riot(url, "league.entries", {"page": "1"})
            entries = _then(body, lambda b: _validate(_ENTRIES, b, "league entries"))
        else:
            kind = tier.lower()
            url = f"{self._platform}/lol/league/v4/{kind}leagues/by-queue/RANKED_SOLO_5x5"
            body = await self._riot(url, "league.apex", {})
            league = _then(body, lambda b: _validate(_LEAGUE, b, "league"))
            entries = _then(league, lambda lg: Ok(lg.entries))
        return _then(
            entries, lambda es: Ok([e.puuid for e in sorted(es, key=lambda e: -e.league_points)])
        )

    async def match_ids(self, player: str, count: int) -> Result[list[str], SourceError]:
        url = f"{self._region}/lol/match/v5/matches/by-puuid/{player}/ids"
        params = {"queue": str(RANKED_SOLO), "type": "ranked", "start": "0", "count": str(count)}
        body = await self._riot(url, "match.ids", params)
        return _then(body, lambda b: _validate(_MATCH_IDS, b, "match ids"))

    async def fetch(
        self, match_id: str, wanted: Callable[[MatchHeader], str | None]
    ) -> Result[Match | Skipped, SourceError]:
        url = f"{self._region}/lol/match/v5/matches/{match_id}"
        body = await self._riot(url, "match", {})
        match _then(body, lambda b: _validate(_MATCH, b, f"match {match_id}")):
            case Err() as e:
                return e
            case Ok(value=payload):
                pass
        reason = wanted(payload.header())
        if reason is not None:
            return Ok(Skipped(reason))
        body = await self._riot(f"{url}/timeline", "timeline", {})
        match _then(body, lambda b: _validate(_TIMELINE, b, f"timeline {match_id}")):
            case Err() as e:
                return e
            case Ok(value=timeline):
                pass
        try:
            return Ok(to_match(payload, timeline))
        except (PayloadError, ValidationError) as e:
            return Err(SourceError("invalid", f"match {match_id}: {_first_line(e)}"))

    async def static_data(self, patch: str) -> Result[StaticData, SourceError]:
        body = await self._get(f"{DATA_DRAGON}/api/versions.json", None, {}, {})
        match _then(body, lambda b: _validate(_VERSIONS, b, "Data Dragon versions")):
            case Err() as e:
                return e
            case Ok(value=versions):
                pass
        version = next((v for v in versions if v.startswith(f"{patch}.")), None)
        if version is None:
            return Err(SourceError("not_found", f"no Data Dragon version for patch {patch}"))
        base = f"{DATA_DRAGON}/cdn/{version}/data/en_US"
        body = await self._get(f"{base}/champion.json", None, {}, {})
        match _then(body, lambda b: _validate(_CHAMPIONS, b, "Data Dragon champions")):
            case Err() as e:
                return e
            case Ok(value=champions):
                pass
        body = await self._get(f"{base}/item.json", None, {}, {})
        match _then(body, lambda b: _validate(_ITEMS, b, "Data Dragon items")):
            case Err() as e:
                return e
            case Ok(value=items):
                pass
        try:
            return Ok(to_static(version, champions, items))
        except PayloadError as e:
            return Err(SourceError("invalid", str(e)))

    def stats(self) -> SourceStats:
        return SourceStats(self._requests, self._retries, self._waited)

    async def close(self) -> None:
        await self._client.aclose()

    async def _riot(
        self, url: str, method: str, params: Mapping[str, str]
    ) -> Result[object, SourceError]:
        return await self._get(url, method, params, self._headers)

    async def _get(
        self,
        url: str,
        method: str | None,
        params: Mapping[str, str],
        headers: Mapping[str, str],
    ) -> Result[object, SourceError]:
        """GET with rate limiting (Riot methods only), retries and exponential backoff."""
        attempt = 0
        while True:
            await self._wait_for_slot(method)
            self._requests += 1
            try:
                response = await self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as e:
                problem = f"{type(e).__name__} on {_path(url)}"
            else:
                if self._limiter is not None and method is not None:
                    self._limiter.update(method, self._clock(), response.headers)
                outcome = self._interpret(response, url)
                if outcome is not None:
                    return outcome
                problem = f"HTTP {response.status_code} on {_path(url)}"
            attempt += 1
            if attempt > MAX_RETRIES:
                return Err(SourceError("unavailable", f"{problem}, gave up after {attempt} tries"))
            self._retries += 1
            delay = min(2.0**attempt, MAX_BACKOFF_SECONDS)
            log.warning("%s; retrying in %.0f s", problem, delay)
            self._waited += delay
            await self._sleep(delay)

    def _interpret(self, response: httpx.Response, url: str) -> Result[object, SourceError] | None:
        """The final outcome of a response, or None to retry it."""
        status = response.status_code
        if status == 200:
            try:
                return Ok(response.json())
            except ValueError:
                return Err(SourceError("invalid", f"{_path(url)} returned invalid JSON"))
        if status == 404:
            return Err(SourceError("not_found", f"{_path(url)} not found"))
        if status in (401, 403):
            return Err(
                SourceError(
                    "unauthorized",
                    f"Riot rejected the API key (HTTP {status}); development keys expire "
                    "every 24 h, regenerate it at developer.riotgames.com",
                )
            )
        if status == 429:
            retry_after = response.headers.get("retry-after", "")
            if retry_after.isdigit() and self._limiter is not None:
                self._limiter.block(self._clock() + int(retry_after))
            return None
        if status >= 500:
            return None
        return Err(SourceError("invalid", f"HTTP {status} on {_path(url)}"))

    async def _wait_for_slot(self, method: str | None) -> None:
        if self._limiter is None or method is None:
            return
        while (wait := self._limiter.wait(method, self._clock())) > 0:
            self._waited += wait
            await self._sleep(wait)
        self._limiter.record(method, self._clock())


def _validate[T](adapter: TypeAdapter[T], body: object, what: str) -> Result[T, SourceError]:
    try:
        return Ok(adapter.validate_python(body))
    except ValidationError as e:
        return Err(SourceError("invalid", f"{what}: {_first_line(e)}"))


def _then[T, U](
    result: Result[T, SourceError], f: Callable[[T], Result[U, SourceError]]
) -> Result[U, SourceError]:
    match result:
        case Ok(value=v):
            return f(v)
        case Err() as e:
            return e


def _path(url: str) -> str:
    """The URL without scheme and host, for messages: never contains the key (a header)."""
    return httpx.URL(url).path


def _first_line(error: Exception) -> str:
    lines = str(error).splitlines()
    return " ".join(lines[:3]) if lines else type(error).__name__
