"""Alpha Vantage OVERVIEW — async HTTP + optional JSON cache (TTL) + shared rate limit."""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

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
from app.data.yfinance_overview import yfinance_av_overview_patch
from app.domain.exceptions import DataProviderError, UpstreamRateLimitError

ALPHA_BASE = "https://www.alphavantage.co/query"


def _overview_has_useful_metrics(overview: dict[str, Any]) -> bool:
    """False для заглушки download-скрипта (только Symbol/Name) — тогда нужен live OVERVIEW."""
    for k in (
        "PERatio",
        "EPS",
        "MarketCapitalization",
        "QuarterlyRevenueGrowthYOY",
        "ReturnOnEquityTTM",
        "DividendYield",
        "DebtToEquityRatio",
    ):
        v = overview.get(k)
        if v is None:
            continue
        s = str(v).strip().lower()
        if s in ("", "none", "n/a", "-"):
            continue
        return True
    for k in ("pe_ratio", "eps", "roe", "revenue_growth", "debt_to_equity", "dividend_yield"):
        v = overview.get(k)
        if isinstance(v, (int, float)) and v == v:
            return True
    return False


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

        if not force and self._fundamentals_cache_fresh(sym):
            cached = await read_fundamentals_json(sym)
            if cached is not None and _overview_has_useful_metrics(cached):
                return cached
            if cached is not None:
                logger.info(
                    "Fundamentals JSON for {} is fresh but без мультипликаторов — yfinance, затем OVERVIEW (AV)",
                    sym,
                )

        if settings.alpha_vantage_yfinance_fallback:
            try:
                yf_merged = await self._overview_yfinance_fallback(sym)
                if _overview_has_useful_metrics(yf_merged):
                    return yf_merged
            except Exception as e:
                logger.info("yfinance fundamentals (preferred) failed for {}: {}", sym, e)

        if not self._api_key:
            cached = await read_fundamentals_json(sym)
            if cached is not None:
                logger.info("Using cached fundamentals for {} (no API key)", sym)
                return cached
            logger.info(
                "No ALPHA_VANTAGE_API_KEY and no raw/fundamentals/{}.json — UI stub",
                sym,
            )
            return {"Symbol": sym, "Name": sym}

        try:
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
            payload = cast(dict[str, Any], r.json())
            _check_alpha_payload(payload)
            if not payload or payload.get("Symbol") is None:
                raise DataProviderError(f"No overview data for symbol {sym}")

            await write_fundamentals_json(sym, payload)
            return payload
        except UpstreamRateLimitError as e:
            if not settings.alpha_vantage_yfinance_fallback:
                raise
            logger.warning(
                "Alpha Vantage OVERVIEW quota/limit for {} — yfinance OVERVIEW fallback",
                sym,
            )
            try:
                return await self._overview_yfinance_fallback(sym)
            except Exception as yfe:
                raise DataProviderError(
                    f"Alpha Vantage rate-limited/quota; yfinance fundamentals fallback failed: {yfe}"
                ) from e

    async def _overview_yfinance_fallback(self, sym: str) -> dict[str, Any]:
        patch = await asyncio.to_thread(yfinance_av_overview_patch, sym)
        cached = await read_fundamentals_json(sym)
        merged: dict[str, Any] = {"Symbol": sym}
        if isinstance(cached, dict):
            merged.update(cached)
        merged.update(patch)
        if not str(merged.get("Name") or "").strip():
            merged["Name"] = sym
        if _overview_has_useful_metrics(merged):
            await write_fundamentals_json(sym, merged)
        return merged
