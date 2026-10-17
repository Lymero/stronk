"""A fake Riot API and Data Dragon as an httpx transport, with a fake clock."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast

import httpx
from riot_builders import DDRAGON_VERSION, ddragon_champions, ddragon_items

from stronk_pipeline.adapters.riot.client import RiotApiSource
from stronk_pipeline.adapters.riot.rate_limit import RateLimiter

type Handler = Callable[[httpx.Request], httpx.Response]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeRiot:
    """Routes by path. `responses` maps a path to a body, or to a list of responses served
    in turn (the last one repeats)."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = {
            "/api/versions.json": [DDRAGON_VERSION, "16.19.1"],
            f"/cdn/{DDRAGON_VERSION}/data/en_US/champion.json": ddragon_champions(),
            f"/cdn/{DDRAGON_VERSION}/data/en_US/item.json": ddragon_items(),
            **responses,
        }
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer: Any = self.responses.get(request.url.path)
        if answer is None:
            return httpx.Response(404, json={"status": {"status_code": 404}})
        if isinstance(answer, list) and answer and isinstance(answer[0], httpx.Response):
            queue = cast("list[httpx.Response]", answer)
            served = queue[0] if len(queue) == 1 else queue.pop(0)
            return httpx.Response(
                served.status_code, headers=served.headers, content=served.content
            )
        return httpx.Response(200, json=answer)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def source(
    riot: FakeRiot | httpx.AsyncBaseTransport,
    clock: FakeClock | None = None,
    limiter: RateLimiter | None = None,
) -> RiotApiSource:
    clock = clock if clock is not None else FakeClock()
    transport = httpx.MockTransport(riot) if isinstance(riot, FakeRiot) else riot
    return RiotApiSource(
        client=httpx.AsyncClient(transport=transport),
        platform="euw1",
        api_key="RGAPI-test",
        limiter=limiter if limiter is not None else RateLimiter(),
        clock=clock,
        sleep=clock.sleep,
    )


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)
