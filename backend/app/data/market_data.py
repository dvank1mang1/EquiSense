"""Alpha Vantage adapter for OHLCV and quotes — async HTTP, Parquet cache, global rate limit."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, cast

import httpx
import pandas as pd
from loguru import logger

from app.core.config import settings
from app.data.av_rate_limit import get_alpha_vantage_limiter
from app.data.ohlcv_merge import merge_ohlcv_history
from app.data.persistence import (
    ohlcv_parquet_path,
    quote_json_path,
    read_ohlcv_parquet,
    write_ohlcv_parquet,
)
from app.data.utils import normalize_ticker
from app.domain.exceptions import (
    DataProviderConfigError,
    DataProviderError,
    UpstreamRateLimitError,
)

ALPHA_BASE = "https://www.alphavantage.co/query"
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _check_alpha_payload(payload: dict[str, Any]) -> None:
    if "Note" in payload or "Information" in payload:
        raise UpstreamRateLimitError(
            "Alpha Vantage rate limit or quota — wait or upgrade key; see response Note/Information."
        )
    if "Error Message" in payload:
        raise DataProviderError(payload["Error Message"])
    if "Warning Message" in payload:
        logger.warning("Alpha Vantage: {}", payload.get("Warning Message"))


def _daily_series_to_df(series: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date_str, bar in series.items():
        rows.append(
            {
                "date": pd.Timestamp(date_str),
                "open": float(bar["1. open"]),
                "high": float(bar["2. high"]),
                "low": float(bar["3. low"]),
                "close": float(bar["4. close"]),
                "volume": int(float(bar["5. volume"])),
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


class MarketDataClient:
    """
    Alpha Vantage TIME_SERIES_DAILY + GLOBAL_QUOTE.

    All calls share one AsyncIntervalRateLimiter (default 12s ≈ 5 req/min free tier).
    """

    def __init__(self, http: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = (api_key or settings.alpha_vantage_api_key or "").strip()
        self._limiter = get_alpha_vantage_limiter(settings.alpha_vantage_min_interval_sec)

    def _cache_path_fresh_for_full(self, ticker: str) -> bool:
        path = ohlcv_parquet_path(ticker)
        if not path.exists():
            return False
        age = time.time() - path.stat().st_mtime
        return age < settings.ohlcv_parquet_cache_max_age_sec

    async def get_daily_ohlcv(
        self, ticker: str, output_size: str = "full", *, skip_cache: bool = False
    ) -> pd.DataFrame:
        sym = normalize_ticker(ticker)
        if output_size not in ("full", "compact"):
            raise DataProviderError("output_size must be 'full' or 'compact'")

        if self._api_key:
            if output_size == "full" and not skip_cache and self._cache_path_fresh_for_full(sym):
                cached = await read_ohlcv_parquet(sym)
                if cached is not None and not cached.empty:
                    logger.debug("OHLCV cache hit for {}", sym)
                    return cached

            df = await self._fetch_daily_ohlcv(sym, output_size)
            await write_ohlcv_parquet(sym, df)
            return df

        cached = await read_ohlcv_parquet(sym)
        if cached is not None and not cached.empty:
            logger.info("Using cached OHLCV for {} (no ALPHA_VANTAGE_API_KEY)", sym)
            return cached

        if settings.alpha_vantage_yfinance_fallback:
            from app.data.yfinance_market import fetch_daily_ohlcv_yfinance

            try:
                df = await asyncio.to_thread(
                    fetch_daily_ohlcv_yfinance, sym, output_size=output_size
                )
                await write_ohlcv_parquet(sym, df)
                logger.info("OHLCV from yfinance for {} (no AV key)", sym)
                return df
            except DataProviderError as e:
                logger.warning("yfinance OHLCV failed for {} without AV key: {}", sym, e)

        raise DataProviderConfigError(
            "Set ALPHA_VANTAGE_API_KEY, enable yfinance fallback, or seed data/raw/ohlcv/{TICKER}.parquet"
        )

    async def refresh_ohlcv(self, ticker: str, *, force_full: bool = False) -> pd.DataFrame:
        """
        Обновить локальный ряд: при наличии истории — compact + merge; иначе или при
        force_full — полная выгрузка TIME_SERIES_DAILY full.
        """
        sym = normalize_ticker(ticker)
        if not self._api_key and not settings.alpha_vantage_yfinance_fallback:
            raise DataProviderConfigError(
                "ALPHA_VANTAGE_API_KEY required to refresh OHLCV from network"
            )
        existing = await read_ohlcv_parquet(sym)
        if force_full or existing is None or existing.empty:
            return await self.get_daily_ohlcv(ticker, output_size="full", skip_cache=True)
        compact = await self._fetch_daily_ohlcv(sym, "compact")
        merged = merge_ohlcv_history(existing, compact)
        await write_ohlcv_parquet(sym, merged)
        return merged

    async def _fetch_daily_ohlcv_alpha(self, sym: str, output_size: str) -> pd.DataFrame:
        await self._limiter.acquire()
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": sym,
            "outputsize": output_size,
            "apikey": self._api_key,
            "datatype": "json",
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
        key = "Time Series (Daily)"
        if key not in payload:
            raise DataProviderError(f"Unexpected Alpha Vantage response (no {key})")
        return _daily_series_to_df(payload[key])

    async def _fetch_daily_ohlcv(self, sym: str, output_size: str) -> pd.DataFrame:
        from app.data.yfinance_market import fetch_daily_ohlcv_yfinance

        if settings.alpha_vantage_yfinance_fallback:
            try:
                return await asyncio.to_thread(
                    fetch_daily_ohlcv_yfinance, sym, output_size=output_size
                )
            except DataProviderError as e:
                logger.info("yfinance OHLCV failed for {} ({}), trying Alpha Vantage", sym, e)

        if not self._api_key:
            raise DataProviderError("No Alpha Vantage API key and yfinance did not return OHLCV")

        try:
            return await self._fetch_daily_ohlcv_alpha(sym, output_size)
        except UpstreamRateLimitError as e:
            if not settings.alpha_vantage_yfinance_fallback:
                raise
            try:
                return await asyncio.to_thread(
                    fetch_daily_ohlcv_yfinance, sym, output_size=output_size
                )
            except DataProviderError as yfe:
                raise DataProviderError(
                    f"Alpha Vantage rate-limited/quota; yfinance OHLCV also failed: {yfe}"
                ) from e

    async def _fetch_alpha_global_quote(self, sym: str) -> dict[str, Any]:
        await self._limiter.acquire()
        params = {
            "function": "GLOBAL_QUOTE",
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
        gq = payload.get("Global Quote") or {}
        if not gq:
            raise DataProviderError("Empty Global Quote — check symbol or API limits")
        return {
            "symbol": gq.get("01. symbol", sym),
            "open": _maybe_float(gq.get("02. open")),
            "high": _maybe_float(gq.get("03. high")),
            "low": _maybe_float(gq.get("04. low")),
            "price": _maybe_float(gq.get("05. price")),
            "volume": _maybe_int(gq.get("06. volume")),
            "latest_trading_day": gq.get("07. latest trading day"),
            "previous_close": _maybe_float(gq.get("08. previous close")),
            "change": _maybe_float(gq.get("09. change")),
            "change_percent": (gq.get("10. change percent") or "").replace("%", "").strip()
            if gq.get("10. change percent")
            else None,
        }

    async def _quote_dict_from_cached_ohlcv(self, sym: str) -> dict[str, Any] | None:
        cached = await read_ohlcv_parquet(sym)
        if cached is None or cached.empty:
            return None
        last = cached.iloc[-1]
        prev = cached.iloc[-2] if len(cached) >= 2 else last
        last_close = _maybe_float(last.get("close"))
        prev_close = _maybe_float(prev.get("close"))
        change = (
            (last_close - prev_close)
            if last_close is not None and prev_close is not None
            else None
        )
        change_percent = (
            f"{(change / prev_close) * 100.0:.4f}"
            if change is not None and prev_close not in (None, 0.0)
            else None
        )
        return {
            "symbol": sym,
            "open": _maybe_float(last.get("open")),
            "high": _maybe_float(last.get("high")),
            "low": _maybe_float(last.get("low")),
            "price": last_close,
            "volume": _maybe_int(last.get("volume")),
            "latest_trading_day": str(last.get("date"))[:10],
            "previous_close": prev_close,
            "change": change,
            "change_percent": change_percent,
            "source": "cached_ohlcv_fallback",
        }

    async def get_current_price(self, ticker: str, *, skip_cache: bool = False) -> dict:
        sym = normalize_ticker(ticker)
        path = quote_json_path(sym)
        if not skip_cache and path.exists():
            age = time.time() - path.stat().st_mtime
            if age < settings.quote_json_cache_max_age_sec:
                return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

        from app.data.yfinance_market import fetch_quote_yfinance

        finnhub_key = (settings.finnhub_api_key or "").strip()
        data: dict[str, Any] | None = None

        if settings.alpha_vantage_yfinance_fallback:
            try:
                data = await asyncio.to_thread(fetch_quote_yfinance, sym)
            except DataProviderError as e:
                logger.debug("yfinance quote (preferred) unavailable for {}: {}", sym, e)

        if data is None and finnhub_key:
            try:
                data = await self._fetch_quote_finnhub(sym, finnhub_key)
            except DataProviderError as e:
                logger.debug("Finnhub quote for {}: {}", sym, e)

        if data is None:
            data = await self._quote_dict_from_cached_ohlcv(sym)

        if data is None and self._api_key:
            try:
                data = await self._fetch_alpha_global_quote(sym)
            except UpstreamRateLimitError as e:
                if not settings.alpha_vantage_yfinance_fallback:
                    raise
                logger.warning(
                    "Alpha Vantage GLOBAL_QUOTE quota/limit for {} — retrying fallbacks",
                    sym,
                )
                try:
                    data = await asyncio.to_thread(fetch_quote_yfinance, sym)
                except DataProviderError as yfe:
                    if finnhub_key:
                        try:
                            data = await self._fetch_quote_finnhub(sym, finnhub_key)
                            logger.warning(
                                "yfinance after AV limit failed for {} ({}); using Finnhub",
                                sym,
                                yfe,
                            )
                        except DataProviderError:
                            data = await self._quote_from_cached_ohlcv_or_raise(sym, yfe, e)
                    else:
                        data = await self._quote_from_cached_ohlcv_or_raise(sym, yfe, e)

        if data is None:
            if not self._api_key and not settings.alpha_vantage_yfinance_fallback:
                raise DataProviderConfigError(
                    "ALPHA_VANTAGE_API_KEY required for live quote (or enable yfinance fallback)"
                )
            raise DataProviderError(
                "No quote from yfinance, Finnhub, cached OHLCV, or Alpha Vantage — check symbol and keys"
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    async def _fetch_quote_finnhub(self, sym: str, token: str) -> dict[str, Any]:
        try:
            r = await self._http.get(
                f"{FINNHUB_BASE}/quote",
                params={"symbol": sym, "token": token},
                timeout=httpx.Timeout(8.0, connect=4.0),
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise DataProviderError(f"Finnhub HTTP {err.response.status_code}") from err
        payload = cast(dict[str, Any], r.json())
        price = _maybe_float(payload.get("c"))
        if price in (None, 0.0):
            raise DataProviderError("Finnhub quote is empty")
        open_ = _maybe_float(payload.get("o"))
        high = _maybe_float(payload.get("h"))
        low = _maybe_float(payload.get("l"))
        prev_close = _maybe_float(payload.get("pc"))
        change = (price - prev_close) if prev_close is not None else None
        change_percent = (
            f"{(change / prev_close) * 100.0:.4f}"
            if change is not None and prev_close not in (None, 0.0)
            else None
        )
        ts = payload.get("t")
        latest = (
            pd.Timestamp(int(ts), unit="s", tz="UTC").strftime("%Y-%m-%d")
            if isinstance(ts, (int, float)) and ts > 0
            else None
        )
        return {
            "symbol": sym,
            "open": open_,
            "high": high,
            "low": low,
            "price": price,
            "volume": None,
            "latest_trading_day": latest,
            "previous_close": prev_close,
            "change": change,
            "change_percent": change_percent,
            "source": "finnhub_fallback",
        }

    async def _quote_from_cached_ohlcv_or_raise(
        self,
        sym: str,
        yfinance_error: DataProviderError,
        root_error: Exception,
    ) -> dict[str, Any]:
        built = await self._quote_dict_from_cached_ohlcv(sym)
        if built is not None:
            logger.warning(
                "yfinance quote fallback failed for {} ({}); using cached OHLCV latest close",
                sym,
                yfinance_error,
            )
            return built
        raise DataProviderError(
            "Alpha Vantage rate-limited/quota; yfinance quote fallback failed and no cached OHLCV"
        ) from root_error

    async def update_incremental(self, ticker: str) -> pd.DataFrame:
        """Alias: merge compact into stored history (или full при первом запуске)."""
        return await self.refresh_ohlcv(ticker, force_full=False)


def _maybe_float(x: str | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _maybe_int(x: str | None) -> int | None:
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except ValueError:
        return None
