import asyncio
import time

import pytest

from app.data.av_rate_limit import AsyncIntervalRateLimiter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiter_spaces_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(d: float) -> None:
        sleeps.append(d)

    import app.data.av_rate_limit as mod

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    lim = AsyncIntervalRateLimiter(min_interval_sec=1.0)
    t0 = time.monotonic()
    await lim.acquire()
    await lim.acquire()
    assert len(sleeps) == 1
    assert sleeps[0] >= 0.99
