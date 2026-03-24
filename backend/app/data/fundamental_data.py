"""Alpha Vantage OVERVIEW — async HTTP + optional JSON cache (TTL) + shared rate limit."""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from app.core.config import settings
from app.data.av_rate_limit import get_alpha_vantage_limiter
from app.data.persistence import (
    fundamentals_json_path,
    read_fundamentals_json,
    write_fundamentals_json,
)
from app.data.utils import normalize_ticker
from app.domain.exceptions import (
    DataProviderConfigError,
    DataProviderError,
    UpstreamRateLimitError,
)

ALPHA_BASE = "https://www.alphavantage.co/query"


def _check_alpha_payload(payload: dict[str, Any]) -> None:
    if "Note" in payload or "Information" in payload:
        raise UpstreamRateLimitError("Alpha Vantage rate limit or quota.")
    if "Error Message" in payload:
        raise DataProviderError(payload["Error Message"])


class FundamentalDataClient:
    """Company overview (annual figures as strings in Alpha Vantage)."""

    def __init__(self, http: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = (api_key or settings.alpha_vantage_api_key or "").strip()
        self._limiter = get_alpha_vantage_limiter(settings.alpha_vantage_min_interval_sec)

    def _fundamentals_cache_fresh(self, sym: str) -> bool:
        path = fundamentals_json_path(sym)
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < settings.fundamentals_json_cache_max_age_sec

    async def get_snapshot(self, ticker: str, *, force: bool = False) -> dict:
        sym = normalize_ticker(ticker)

        if not self._api_key:
            cached = await read_fundamentals_json(sym)
            if cached is not None:
                logger.info("Using cached fundamentals for {} (no API key)", sym)
                return cached
            raise DataProviderConfigError(
                "Set ALPHA_VANTAGE_API_KEY or place data/raw/fundamentals/{TICKER}.json"
            )

        if not force and self._fundamentals_cache_fresh(sym):
            cached = await read_fundamentals_json(sym)
            if cached is not None:
                return cached

        await self._limiter.acquire()
        params = {
            "function": "OVERVIEW",
            "symbol": sym,
            "apikey": self._api_key,
        }
        try:
            r = await self._http.get(ALPHA_BASE, params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise UpstreamRateLimitError("Alpha Vantage HTTP 429") from e
            raise DataProviderError(f"Alpha Vantage HTTP {e.response.status_code}") from e
        payload = r.json()
        _check_alpha_payload(payload)
        if not payload or payload.get("Symbol") is None:
            raise DataProviderError(f"No overview data for symbol {sym}")

        await write_fundamentals_json(sym, payload)
        return payload
