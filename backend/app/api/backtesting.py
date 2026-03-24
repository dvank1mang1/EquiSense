from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/{ticker}")
async def run_backtest(
    ticker: str,
    model: str | None = Query("model_d"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    initial_capital: float = Query(10000.0, ge=100),
):
    """
    Запустить backtesting стратегии на основе предсказаний модели.
    Возвращает: cumulative return, Sharpe ratio, max drawdown, win rate, equity curve.
    """
    return {
        "ticker": ticker.upper(),
        "model": model,
        "start_date": start_date,
        "end_date": end_date,
        "metrics": {
            "cumulative_return": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "win_rate": None,
        },
        "equity_curve": [],
    }


@router.get("/{ticker}/compare")
async def compare_backtest_models(
    ticker: str,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Сравнение backtesting результатов всех 4 моделей."""
    return {
        "ticker": ticker.upper(),
        "comparison": {
            "model_a": {},
            "model_b": {},
            "model_c": {},
            "model_d": {},
        },
    }
