from __future__ import annotations

import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine


@pytest.mark.unit
def test_backtest_engine_run_returns_metrics_and_curve() -> None:
    price_df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=6, freq="D"),
            "close": [100.0, 101.0, 103.0, 102.0, 104.0, 106.0],
        }
    )
    predictions_df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=6, freq="D"),
            "signal": ["Hold", "Buy", "Buy", "Hold", "Buy", "Sell"],
            "probability": [0.5, 0.6, 0.7, 0.4, 0.65, 0.3],
        }
    )

    engine = BacktestEngine(initial_capital=10_000.0)
    out = engine.run(
        price_df=price_df, predictions_df=predictions_df, ticker="AAPL", model_id="model_d"
    )

    assert out.ticker == "AAPL"
    assert out.model_id == "model_d"
    assert out.total_trades >= 1
    assert -1.0 <= out.max_drawdown <= 0.0
    assert 0.0 <= out.win_rate <= 1.0
    assert len(out.equity_curve) == len(price_df)
