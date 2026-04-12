import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.contracts.data_providers import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
)
from app.core.config import settings
from app.data.local_artifacts import summarize_data_artifacts
from app.data.news_filter import filter_news_for_ticker
from app.data.periods import ohlcv_tail_by_period
from app.data.persistence import (
    list_cached_ohlcv_tickers,
    read_fundamentals_json,
    read_news_json_sync,
    read_ohlcv_parquet,
    write_news_json_sync,
)
from app.data.serialization import ohlcv_rows
from app.data.utils import normalize_ticker
from app.domain.exceptions import (
    DataProviderConfigError,
    DataProviderError,
    UpstreamRateLimitError,
)
from app.features.fundamental import enrich_overview_for_ui
from app.features.sentiment import attach_finbert_to_news_items
from app.features.technical import TechnicalFeatureEngineer
from app.services.dependencies import (
    get_fundamental_data_provider,
    get_market_data_provider,
    get_news_data_provider,
)

router = APIRouter()


async def _enrich_fundamentals_async(payload: dict[str, Any]) -> dict[str, Any]:
    """enrich_overview_for_ui дергает yfinance синхронно — только в thread pool, иначе блокируется весь ASGI."""

    def _run() -> dict[str, Any]:
        try:
            return enrich_overview_for_ui(payload)
        except Exception as e:
            logger.warning("enrich_overview_for_ui failed: {}", e)
            return dict(payload)

    return await asyncio.to_thread(_run)


class StockRefreshBody(BaseModel):
    """Что обновить с API; без ключа соответствующие блоки вернут ошибку в ответе."""

    ohlcv: bool = True
    force_full: bool = Field(
        False,
        description="Полная выгрузка daily вместо merge compact→full",
    )
    fundamentals: bool = True
    quote: bool = True
    news: bool = Field(
        False,
        description="Загрузить заголовки в data/raw/news/{TICKER}.json; тональность в UI — через GET /news (FinBERT).",
    )


def _raise_http_from_data_error(e: Exception) -> None:
    if isinstance(e, UpstreamRateLimitError):
        raise HTTPException(status_code=429, detail=str(e)) from e
    if isinstance(e, DataProviderConfigError):
        raise HTTPException(status_code=503, detail=str(e)) from e
    if isinstance(e, DataProviderError):
        raise HTTPException(status_code=502, detail=str(e)) from e
    raise e


@router.get("/")
async def list_supported_tickers():
    """Тикеры, для которых есть локальный кэш OHLCV (Parquet)."""
    tickers = await list_cached_ohlcv_tickers()
    return {"tickers": tickers}


@router.get("/{ticker}/artifacts")
async def get_local_data_artifacts(ticker: str):
    """
    Локальные файлы raw/processed для тикера: путь, есть ли файл, размер, возраст (mtime).
    Не требует GPU; удобно проверить кэш и ETL до запуска FinBERT.
    """
    sym = normalize_ticker(ticker)
    return await asyncio.to_thread(summarize_data_artifacts, sym)


@router.get("/{ticker}")
async def get_stock_overview(
    ticker: str,
    market: MarketDataProvider = Depends(get_market_data_provider),
    fundamental: FundamentalDataProvider = Depends(get_fundamental_data_provider),
):
    """Котировка (Alpha Vantage) + снимок фундаментала; при отсутствии ключа — цена из кэша OHLCV."""
    sym = normalize_ticker(ticker)
    logger.info("stocks.overview start ticker={}", sym)
    quote: dict[str, Any] | None = None
    quote_meta: dict[str, str] = {}

    try:
        quote = await market.get_current_price(ticker)
    except DataProviderConfigError as e:
        quote_meta["quote"] = str(e)
        cached = await read_ohlcv_parquet(sym)
        if cached is not None and not cached.empty:
            last = cached.iloc[-1]
            quote = {
                "symbol": sym,
                "price": float(last["close"]),
                "latest_trading_day": pd_ts_to_date_str(last["date"]),
                "source": "cached_ohlcv",
            }
    except (DataProviderError, UpstreamRateLimitError) as e:
        _raise_http_from_data_error(e)

    fundamentals: dict[str, Any] = {}
    try:
        fundamentals = await fundamental.get_snapshot(ticker, force=False)
    except DataProviderConfigError as e:
        fundamentals = {"_error": str(e)}
    except (DataProviderError, UpstreamRateLimitError) as e:
        _raise_http_from_data_error(e)

    if "_error" not in fundamentals:
        fundamentals = await _enrich_fundamentals_async(fundamentals)

    return {
        "ticker": sym,
        "quote": quote,
        "quote_meta": quote_meta or None,
        "fundamentals": fundamentals,
    }


def pd_ts_to_date_str(d: Any) -> str:
    strftime = getattr(d, "strftime", None)
    if callable(strftime):
        return str(strftime("%Y-%m-%d"))
    return str(d)[:10]


def _to_finite_float(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    # NaN check without importing math.
    if x != x:
        return None
    return x


@router.get("/{ticker}/history")
async def get_price_history(
    ticker: str,
    period: str | None = Query("1y", description="1m, 3m, 6m, 1y, 2y, max"),
    market: MarketDataProvider = Depends(get_market_data_provider),
):
    """OHLCV; источник — API или локальный Parquet."""
    sym = normalize_ticker(ticker)
    logger.info("stocks.history start ticker={} period={}", sym, period or "1y")
    # Prefer local cache for stability under load; fallback to upstream only if cache is absent.
    cached = await read_ohlcv_parquet(sym)
    if cached is not None and not cached.empty:
        df = cached
    else:
        try:
            df = await market.get_daily_ohlcv(ticker, output_size="full", skip_cache=False)
        except DataProviderConfigError:
            raise HTTPException(
                status_code=503,
                detail="No API key and no cached OHLCV for this ticker.",
            ) from None
        except (DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    if period and period not in ("1m", "3m", "6m", "1y", "2y", "max"):
        raise HTTPException(status_code=422, detail="Invalid period")

    sliced = ohlcv_tail_by_period(df, period or "1y")
    return {
        "ticker": sym,
        "period": period,
        "candles": ohlcv_rows(sliced),
    }


@router.get("/{ticker}/fundamentals")
async def get_fundamentals(
    ticker: str,
    fundamental: FundamentalDataProvider = Depends(get_fundamental_data_provider),
):
    sym = normalize_ticker(ticker)
    try:
        data = await fundamental.get_snapshot(ticker, force=False)
    except DataProviderConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except (DataProviderError, UpstreamRateLimitError) as e:
        _raise_http_from_data_error(e)
    return {"ticker": sym, "fundamentals": await _enrich_fundamentals_async(data)}


@router.get("/{ticker}/news")
async def get_news(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
    news: NewsDataProvider = Depends(get_news_data_provider),
):
    """Заголовки: live API; фильтр релевантности; FinBERT (если news_finbert_enabled); кэш raw/news при сбое."""
    sym = normalize_ticker(ticker)
    warning: str | None = None
    items: list[dict[str, Any]] = []

    try:
        items = await news.get_recent(ticker, limit=limit)
    except (DataProviderError, UpstreamRateLimitError) as e:
        warning = str(e)
        logger.warning("stocks.news live fetch failed ticker={} : {}", sym, e)

    if not items:
        cached = await asyncio.to_thread(read_news_json_sync, sym)
        if cached:
            take = min(len(cached), max(limit * 4, 40))
            items = cached[:take]
            if warning:
                warning = "Показаны сохранённые заголовки (live API недоступен)."

    overview = await read_fundamentals_json(sym)
    company_name: str | None = None
    if isinstance(overview, dict):
        raw_name = overview.get("Name")
        if isinstance(raw_name, str) and raw_name.strip():
            company_name = raw_name.strip()

    items = filter_news_for_ticker(items, sym, company_name=company_name, limit=limit)

    if settings.news_finbert_enabled and items:

        def _run_finbert() -> None:
            try:
                attach_finbert_to_news_items(items)
            except Exception as e:
                logger.warning("stocks.news FinBERT failed ticker={}: {}", sym, e)

        await asyncio.to_thread(_run_finbert)

    return {"ticker": sym, "news": items, "warning": warning}


@router.post("/{ticker}/refresh")
async def refresh_stock_data(
    ticker: str,
    body: StockRefreshBody,
    market: MarketDataProvider = Depends(get_market_data_provider),
    fundamental: FundamentalDataProvider = Depends(get_fundamental_data_provider),
    news: NewsDataProvider = Depends(get_news_data_provider),
):
    """Принудительное обновление кэшей OHLCV / фундаментала / котировки (с учётом rate limit)."""
    sym = normalize_ticker(ticker)
    logger.info(
        "stocks.refresh start ticker={} ohlcv={} fundamentals={} quote={} news={} force_full={}",
        sym,
        body.ohlcv,
        body.fundamentals,
        body.quote,
        body.news,
        body.force_full,
    )
    result: dict[str, Any] = {
        "ticker": sym,
        "ohlcv": None,
        "fundamentals": None,
        "quote": None,
        "news": None,
    }

    if body.ohlcv:
        try:
            df = await market.refresh_ohlcv(ticker, force_full=body.force_full)
            last_d = pd_ts_to_date_str(df["date"].iloc[-1]) if len(df) else None
            result["ohlcv"] = {"rows": int(len(df)), "last_date": last_d}
        except (DataProviderConfigError, DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    if body.fundamentals:
        try:
            result["fundamentals"] = await fundamental.get_snapshot(ticker, force=True)
        except DataProviderConfigError as e:
            result["fundamentals"] = {"_error": str(e)}
        except (DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    if body.quote:
        try:
            result["quote"] = await market.get_current_price(ticker, skip_cache=True)
        except DataProviderConfigError as e:
            result["quote"] = None
            result["quote_error"] = str(e)
        except (DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    if body.news:
        try:
            items = await news.get_recent(ticker, limit=100)
            path = await asyncio.to_thread(write_news_json_sync, sym, items)
            result["news"] = {"cached_path": str(path), "count": len(items)}
        except (DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)
    logger.info("stocks.refresh done ticker={}", sym)
    return result


@router.get("/{ticker}/indicators")
async def get_technical_indicators(
    ticker: str,
    market: MarketDataProvider = Depends(get_market_data_provider),
):
    """Текущие technical indicators из OHLCV (кэш или провайдер)."""
    sym = normalize_ticker(ticker)
    logger.info("stocks.indicators start ticker={}", sym)
    df = await read_ohlcv_parquet(sym)
    if df is None or df.empty:
        try:
            df = await market.get_daily_ohlcv(sym, output_size="full", skip_cache=False)
        except (DataProviderConfigError, DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    if df is None or df.empty:
        raise HTTPException(
            status_code=503, detail="No OHLCV data available for indicator calculation."
        )

    engineer = TechnicalFeatureEngineer()
    feats = await asyncio.to_thread(engineer.compute, df)
    if feats.empty:
        raise HTTPException(status_code=503, detail="Technical features are empty.")
    last = feats.iloc[-1]
    payload = {
        "ticker": sym,
        "date": pd_ts_to_date_str(last["date"]),
        "returns": _to_finite_float(last.get("returns")),
        "volatility": _to_finite_float(last.get("volatility")),
        "rsi": _to_finite_float(last.get("rsi")),
        "macd": _to_finite_float(last.get("macd")),
        "macd_signal": _to_finite_float(last.get("macd_signal")),
        "macd_hist": _to_finite_float(last.get("macd_hist")),
        "sma_20": _to_finite_float(last.get("sma_20")),
        "sma_50": _to_finite_float(last.get("sma_50")),
        "sma_200": _to_finite_float(last.get("sma_200")),
        "bb_upper": _to_finite_float(last.get("bb_upper")),
        "bb_lower": _to_finite_float(last.get("bb_lower")),
        "bb_width": _to_finite_float(last.get("bb_width")),
        "momentum": _to_finite_float(last.get("momentum")),
    }
    logger.info("stocks.indicators done ticker={} date={}", sym, payload["date"])
    return payload
