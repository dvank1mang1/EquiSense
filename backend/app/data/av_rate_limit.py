"""
Global pacing for Alpha Vantage HTTP calls (free tier ~5 req/min → min 12s between calls).

Shared across MarketDataClient and FundamentalDataClient so OVERVIEW + TIME_SERIES
don't burst the same API key.
"""

from __future__ import annotations

import asyncio
import time


class AsyncIntervalRateLimiter:
    """At least `min_interval_sec` between consecutive `acquire()` completions."""

    def __init__(self, min_interval_sec: float) -> None:
        self._min = min_interval_sec
        self._lock = asyncio.Lock()
        self._last_release = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last_release + self._min - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_release = time.monotonic()


# Module singleton — one gate per process for Alpha Vantage
_alpha_vantage_limiter: AsyncIntervalRateLimiter | None = None


def get_alpha_vantage_limiter(min_interval_sec: float) -> AsyncIntervalRateLimiter:
    global _alpha_vantage_limiter
    if _alpha_vantage_limiter is None:
        _alpha_vantage_limiter = AsyncIntervalRateLimiter(min_interval_sec)
    return _alpha_vantage_limiter
