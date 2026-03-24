from datetime import date

from pydantic import BaseModel


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
    sector: str | None = None
    market_cap: float | None = None
    price: float
    change_pct: float


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: str
    sentiment: str | None = None
    sentiment_score: float | None = None


class TechnicalIndicators(BaseModel):
    ticker: str
    date: date
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_mid: float | None = None
    momentum: float | None = None
    volatility: float | None = None


class FundamentalMetrics(BaseModel):
    ticker: str
    pe_ratio: float | None = None
    eps: float | None = None
    revenue_growth: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    market_cap: float | None = None
    dividend_yield: float | None = None
