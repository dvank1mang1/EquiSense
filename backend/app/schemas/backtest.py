from datetime import date

from pydantic import BaseModel


class BacktestRequest(BaseModel):
    ticker: str
    model: str = "model_d"
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = 10000.0


class EquityPoint(BaseModel):
    date: date
    equity: float
    return_pct: float
    benchmark_equity: float | None = None


class BacktestMetrics(BaseModel):
    cumulative_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int


class BacktestResponse(BaseModel):
    ticker: str
    model: str
    start_date: date
    end_date: date
    initial_capital: float
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]


class BacktestCompareEntry(BaseModel):
    model: str
    ok: bool
    metrics: BacktestMetrics | None = None
    error: str | None = None


class BacktestCompareResponse(BaseModel):
    ticker: str
    comparison: dict[str, BacktestCompareEntry]
