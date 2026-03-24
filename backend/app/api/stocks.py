from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.contracts.data_providers import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
)
from app.data.periods import ohlcv_tail_by_period
from app.data.persistence import (
    list_cached_ohlcv_tickers,
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
from app.services.dependencies import (
    get_fundamental_data_provider,
    get_market_data_provider,
    get_news_data_provider,
)

router = APIRouter()


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
        description="Fetch headlines and cache under data/raw/news/{TICKER}.json (FinBERT runs in batch ETL, not here).",
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


@router.get("/{ticker}")
async def get_stock_overview(
    ticker: str,
    market: MarketDataProvider = Depends(get_market_data_provider),
    fundamental: FundamentalDataProvider = Depends(get_fundamental_data_provider),
):
    """Котировка (Alpha Vantage) + снимок фундаментала; при отсутствии ключа — цена из кэша OHLCV."""
    sym = normalize_ticker(ticker)
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


@router.get("/{ticker}/history")
async def get_price_history(
    ticker: str,
    period: str | None = Query("1y", description="1m, 3m, 6m, 1y, 2y, max"),
    market: MarketDataProvider = Depends(get_market_data_provider),
):
    """OHLCV; источник — API или локальный Parquet."""
    sym = normalize_ticker(ticker)
    try:
        df = await market.get_daily_ohlcv(ticker, output_size="full", skip_cache=False)
    except DataProviderConfigError:
        df = await read_ohlcv_parquet(sym)
        if df is None or df.empty:
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
    return {"ticker": sym, "fundamentals": data}


@router.get("/{ticker}/news")
async def get_news(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
    news: NewsDataProvider = Depends(get_news_data_provider),
):
    sym = normalize_ticker(ticker)
    try:
        items = await news.get_recent(ticker, limit=limit)
    except (DataProviderError, UpstreamRateLimitError) as e:
        _raise_http_from_data_error(e)
    return {"ticker": sym, "news": items}


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
            path = write_news_json_sync(sym, items)
            result["news"] = {"cached_path": str(path), "count": len(items)}
        except (DataProviderError, UpstreamRateLimitError) as e:
            _raise_http_from_data_error(e)

    return result


@router.get("/{ticker}/indicators")
async def get_technical_indicators(ticker: str):
    """Индикаторы появятся после слоя feature engineering (см. /history + FE)."""
    return {
        "ticker": normalize_ticker(ticker),
        "indicators": {},
        "note": "Use processed features from FeatureStore once technical.py is wired.",
    }
