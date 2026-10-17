import pytest

from stronk_pipeline.adapters.riot.rate_limit import WINDOW_MARGIN, RateLimiter


def fill(limiter: RateLimiter, count: int, now: float = 0.0, method: str = "m") -> None:
    for _ in range(count):
        limiter.record(method, now)


def test_no_wait_below_the_limit() -> None:
    limiter = RateLimiter(((3, 1.0),))
    fill(limiter, 2)
    assert limiter.wait("m", 0.0) == 0.0


def test_waits_until_the_oldest_request_leaves_the_window() -> None:
    limiter = RateLimiter(((2, 10.0),))
    limiter.record("m", 0.0)
    limiter.record("m", 4.0)
    assert limiter.wait("m", 5.0) == pytest.approx(5.0 + WINDOW_MARGIN)
    assert limiter.wait("m", 10.0 + WINDOW_MARGIN + 0.01) == 0.0


def test_the_strictest_window_wins() -> None:
    limiter = RateLimiter(((20, 1.0), (3, 120.0)))
    fill(limiter, 3)
    assert limiter.wait("m", 2.0) == pytest.approx(118.0 + WINDOW_MARGIN)


def test_method_limits_come_from_headers_and_apply_per_method() -> None:
    limiter = RateLimiter(((100, 1.0),))
    limiter.update("match", 0.0, {"x-method-rate-limit": "2:10"})
    fill(limiter, 2, method="match")
    assert limiter.wait("match", 1.0) > 0
    assert limiter.wait("timeline", 1.0) == 0.0


def test_app_limits_are_replaced_by_headers_keeping_history() -> None:
    limiter = RateLimiter(((100, 120.0),))
    fill(limiter, 5)
    limiter.update("m", 0.0, {"x-app-rate-limit": "5:120,20:1"})
    assert limiter.wait("m", 1.0) > 100


def test_catches_up_with_higher_counts_from_riot() -> None:
    limiter = RateLimiter(((10, 120.0),))
    limiter.record("m", 0.0)
    limiter.update("m", 0.0, {"x-app-rate-limit-count": "10:120"})
    assert limiter.wait("m", 1.0) > 100


def test_block_from_retry_after() -> None:
    limiter = RateLimiter()
    limiter.block(30.0)
    assert limiter.wait("m", 10.0) == pytest.approx(20.0)


@pytest.mark.parametrize("header", ["", "garbage", "20:0", "x:1", ":", "1:1:1"])
def test_malformed_headers_are_ignored(header: str) -> None:
    limiter = RateLimiter(((2, 1.0),))
    limiter.update("m", 0.0, {"x-app-rate-limit": header, "x-method-rate-limit-count": header})
    fill(limiter, 1)
    assert limiter.wait("m", 0.0) == 0.0
