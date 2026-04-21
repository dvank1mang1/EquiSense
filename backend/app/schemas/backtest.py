from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

from app.backtesting.baseline_signals import is_baseline_strategy
from app.domain.identifiers import ModelId


def validate_backtest_model_id(v: str) -> str:
    """Rollout ML ids or simple rule baselines (no joblib)."""
    s = str(v).strip()
    if not s:
        raise ValueError("model must be non-empty")
    if is_baseline_strategy(s):
        return s.lower()
    try:
        return ModelId(s).value
    except ValueError as e:
        raise ValueError(
            f"unknown backtest model or strategy: {v!r}; "
            f"use a ModelId value or baseline_buy_hold / baseline_ma_200"
        ) from e


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
    turnover: float | None = None


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


class BacktestJobPayload(BaseModel):
    type: Literal["backtest_single"] = "backtest_single"
    run_id: str
    ticker: str
    model: str
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = 10000.0

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str) -> str:
        return validate_backtest_model_id(v)


class BacktestRunJobBody(BaseModel):
    model: str = ModelId.MODEL_D.value
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = 10000.0

    @field_validator("model")
    @classmethod
    def _validate_model_body(cls, v: str) -> str:
        return validate_backtest_model_id(v)
