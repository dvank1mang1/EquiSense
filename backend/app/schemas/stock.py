from pydantic import BaseModel
from typing import Optional
from datetime import date


class CandleData(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockPrice(BaseModel):
    ticker: str
    price: float
    change: float
    change_pct: float
    volume: int
    timestamp: str


class StockOverview(BaseModel):
    ticker: str
    name: str
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    price: float
    change_pct: float


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: str
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None


class TechnicalIndicators(BaseModel):
    ticker: str
    date: date
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_mid: Optional[float] = None
    momentum: Optional[float] = None
    volatility: Optional[float] = None


class FundamentalMetrics(BaseModel):
    ticker: str
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    market_cap: Optional[float] = None
    dividend_yield: Optional[float] = None
