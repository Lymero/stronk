"""Riot rate limits: app-wide and per-method windows, learned from response headers.

Riot sends limits as `X-App-Rate-Limit: 20:1,100:120` (20 requests per second, 100 per two
minutes) and current usage as `X-App-Rate-Limit-Count: 3:1,45:120`, and the same pair per
method (`X-Method-Rate-Limit`). We keep a sliding window of our own request times per limit,
which is never looser than Riot's fixed windows, and catch up with Riot's counts when they are
higher than ours (other processes using the key, or requests we didn't see finish).

Pure: time is passed in, nothing sleeps here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

type Limits = tuple[tuple[int, float], ...]
"""(requests, seconds) pairs."""

DEV_KEY_LIMITS: Limits = ((20, 1.0), (100, 120.0))
"""Development key limits, used until Riot's headers say otherwise."""
WINDOW_MARGIN = 0.25
"""Seconds added to every window to absorb clock and network skew."""


@dataclass
class _Window:
    limit: int
    seconds: float
    stamps: deque[float] = field(default_factory=deque[float])

    def trim(self, now: float) -> None:
        while self.stamps and self.stamps[0] <= now - self.seconds - WINDOW_MARGIN:
            self.stamps.popleft()

    def wait(self, now: float) -> float:
        self.trim(now)
        if len(self.stamps) < self.limit:
            return 0.0
        return self.stamps[len(self.stamps) - self.limit] + self.seconds + WINDOW_MARGIN - now


class RateLimiter:
    def __init__(self, app_limits: Limits = DEV_KEY_LIMITS) -> None:
        self._app = _windows(app_limits)
        self._methods: dict[str, list[_Window]] = {}
        self._blocked_until = 0.0

    def wait(self, method: str, now: float) -> float:
        """Seconds to wait before a request to `method` fits in every window."""
        windows = [*self._app, *self._methods.get(method, [])]
        return max([self._blocked_until - now, *(w.wait(now) for w in windows), 0.0])

    def record(self, method: str, now: float) -> None:
        for window in (*self._app, *self._methods.get(method, [])):
            window.stamps.append(now)

    def block(self, until: float) -> None:
        """Riot said to retry after `until` (a 429 with Retry-After)."""
        self._blocked_until = max(self._blocked_until, until)

    def update(self, method: str, now: float, headers: Mapping[str, str]) -> None:
        """Adopt the limits and counts in a response's headers."""
        app = _parse(headers.get("x-app-rate-limit"))
        if app:
            self._app = _adopt(self._app, app)
        method_limits = _parse(headers.get("x-method-rate-limit"))
        if method_limits:
            self._methods[method] = _adopt(self._methods.get(method, []), method_limits)
        _catch_up(self._app, _parse(headers.get("x-app-rate-limit-count")), now)
        _catch_up(
            self._methods.get(method, []), _parse(headers.get("x-method-rate-limit-count")), now
        )


def _windows(limits: Limits) -> list[_Window]:
    return [_Window(limit, seconds) for limit, seconds in limits]


def _adopt(current: Sequence[_Window], limits: Limits) -> list[_Window]:
    """New limits, keeping request history for windows of the same length."""
    history = {w.seconds: w.stamps for w in current}
    return [
        _Window(limit, seconds, history.get(seconds, deque[float]())) for limit, seconds in limits
    ]


def _catch_up(windows: Sequence[_Window], counts: Limits, now: float) -> None:
    for count, seconds in counts:
        for window in windows:
            if window.seconds == seconds:
                window.trim(now)
                window.stamps.extend([now] * max(count - len(window.stamps), 0))


def _parse(header: str | None) -> Limits:
    """ "20:1,100:120" -> ((20, 1.0), (100, 120.0)); malformed parts are ignored."""
    if not header:
        return ()
    pairs: list[tuple[int, float]] = []
    for part in header.split(","):
        count, _, seconds = part.strip().partition(":")
        if count.isdigit() and seconds.isdigit() and int(seconds) > 0:
            pairs.append((int(count), float(seconds)))
    return tuple(pairs)
