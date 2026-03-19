from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/")
async def list_supported_tickers():
    """Список поддерживаемых тикеров."""
    return {"tickers": []}


@router.get("/{ticker}")
async def get_stock_overview(ticker: str):
    """Текущая цена, базовая информация по тикеру."""
    return {"ticker": ticker.upper(), "data": None}


@router.get("/{ticker}/history")
async def get_price_history(
    ticker: str,
    period: Optional[str] = Query("1y", description="1m, 3m, 6m, 1y, 2y"),
):
    """OHLCV история по тикеру."""
    return {"ticker": ticker.upper(), "period": period, "candles": []}


@router.get("/{ticker}/fundamentals")
async def get_fundamentals(ticker: str):
    """Фундаментальные показатели: P/E, EPS, ROE, и т.д."""
    return {"ticker": ticker.upper(), "fundamentals": {}}


@router.get("/{ticker}/news")
async def get_news(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Последние новости по тикеру с sentiment score."""
    return {"ticker": ticker.upper(), "news": []}


@router.get("/{ticker}/indicators")
async def get_technical_indicators(ticker: str):
    """Технические индикаторы: RSI, MACD, BB, и т.д."""
    return {"ticker": ticker.upper(), "indicators": {}}
