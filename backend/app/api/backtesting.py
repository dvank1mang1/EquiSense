from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.domain.exceptions import BacktestDependencyError, BacktestInputError
from app.domain.identifiers import ModelId
from app.schemas.backtest import (
    BacktestCompareEntry,
    BacktestCompareResponse,
    BacktestMetrics,
    BacktestResponse,
)
from app.schemas.common import ErrorResponse
from app.services.backtesting_service import BacktestingService
from app.services.dependencies import get_backtesting_service

router = APIRouter()


@router.get(
    "/{ticker}",
    response_model=BacktestResponse,
    summary="Run model backtest for one ticker",
    responses={
        200: {
            "description": "Backtest completed",
            "content": {
                "application/json": {
                    "example": {
                        "ticker": "AAPL",
                        "model": "model_d",
                        "start_date": "2024-01-01",
                        "end_date": "2024-03-29",
                        "initial_capital": 10000.0,
                        "metrics": {
                            "cumulative_return": 0.1432,
                            "annualized_return": 0.271,
                            "sharpe_ratio": 1.54,
                            "max_drawdown": -0.082,
                            "win_rate": 0.58,
                            "total_trades": 31,
                        },
                        "equity_curve": [
                            {
                                "date": "2024-01-01",
                                "equity": 10000.0,
                                "return_pct": 0.0,
                                "benchmark_equity": 10000.0,
                            }
                        ],
                    }
                }
            },
        },
        404: {"description": "Model artifact missing", "model": ErrorResponse},
        422: {"description": "Invalid date range / empty slice", "model": ErrorResponse},
    },
)
async def run_backtest(
    ticker: str,
    model: ModelId = Query(ModelId.MODEL_D),
    start_date: date | None = Query(None, description="YYYY-MM-DD"),
    end_date: date | None = Query(None, description="YYYY-MM-DD"),
    initial_capital: float = Query(10000.0, ge=100),
    service: BacktestingService = Depends(get_backtesting_service),
):
    sym = ticker.strip().upper()
    logger.info(
        "backtesting.run start ticker={} model={} start={} end={} initial_capital={}",
        sym,
        model.value,
        start_date,
        end_date,
        initial_capital,
    )
    try:
        resp = await service.run_single(
            ticker=ticker,
            model=model,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
        logger.info(
            "backtesting.run done ticker={} model={} sharpe={} trades={}",
            sym,
            model.value,
            resp.metrics.sharpe_ratio,
            resp.metrics.total_trades,
        )
        return resp
    except BacktestDependencyError as e:
        logger.warning("backtesting.run dependency_error ticker={} model={} err={}", sym, model.value, e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BacktestInputError as e:
        logger.warning("backtesting.run input_error ticker={} model={} err={}", sym, model.value, e)
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get(
    "/{ticker}/compare",
    response_model=BacktestCompareResponse,
    summary="Compare backtest results across models",
    responses={
        200: {
            "description": "Comparison completed",
            "content": {
                "application/json": {
                    "example": {
                        "ticker": "AAPL",
                        "comparison": {
                            "model_a": {
                                "model": "model_a",
                                "ok": True,
                                "metrics": {
                                    "cumulative_return": 0.102,
                                    "annualized_return": 0.189,
                                    "sharpe_ratio": 1.22,
                                    "max_drawdown": -0.095,
                                    "win_rate": 0.55,
                                    "total_trades": 28,
                                },
                                "error": None,
                            },
                            "model_d": {
                                "model": "model_d",
                                "ok": False,
                                "metrics": None,
                                "error": "Model file not found: data/models/model_d.joblib",
                            },
                        },
                    }
                }
            },
        }
    },
)
async def compare_backtest_models(
    ticker: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    initial_capital: float = Query(10000.0, ge=100),
    service: BacktestingService = Depends(get_backtesting_service),
):
    """Сравнение backtesting результатов всех 4 моделей."""
    sym = ticker.strip().upper()
    logger.info(
        "backtesting.compare start ticker={} start={} end={} initial_capital={}",
        sym,
        start_date,
        end_date,
        initial_capital,
    )
    rows = await service.compare_models(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    comparison = {}
    for k, v in rows.items():
        metrics = None
        if v.metrics is not None:
            metrics = BacktestMetrics(
                cumulative_return=float(v.metrics["cumulative_return"]),
                annualized_return=float(v.metrics["annualized_return"]),
                sharpe_ratio=float(v.metrics["sharpe_ratio"]),
                max_drawdown=float(v.metrics["max_drawdown"]),
                win_rate=float(v.metrics["win_rate"]),
                total_trades=int(v.metrics["total_trades"]),
            )
        comparison[k] = BacktestCompareEntry(
            model=v.model,
            ok=v.ok,
            metrics=metrics,
            error=v.error,
        )
    resp = BacktestCompareResponse(
        ticker=ticker.strip().upper(),
        comparison=comparison,
    )
    ok_count = sum(1 for row in comparison.values() if row.ok)
    logger.info("backtesting.compare done ticker={} ok_models={}/4", sym, ok_count)
    return resp
