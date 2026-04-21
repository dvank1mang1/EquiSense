from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtesting.baseline_signals import (
    baseline_predictions_for,
    buy_hold_predictions,
    ma_trend_predictions,
    mean_reversion_volume_predictions,
    momentum_top_k_predictions,
)


@pytest.mark.unit
def test_buy_hold_all_strong_buy() -> None:
    price = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "close": [10.0, 10.5, 11.0, 10.8, 11.2],
        }
    )
    p = buy_hold_predictions(price)
    assert (p["signal"] == "Strong Buy").all()
    assert len(p) == 5


@pytest.mark.unit
def test_ma_trend_requires_window_bars_before_long() -> None:
    n = 210
    close = pd.Series(range(n), dtype=float) + 100.0
    price = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=n, freq="D"), "close": close})
    p = ma_trend_predictions(price, window=200)
    assert p["signal"].iloc[:199].eq("Hold").all()
    assert p["signal"].iloc[-1] == "Buy"


@pytest.mark.unit
def test_momentum_top_k_produces_signals() -> None:
    n = 80
    price = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "close": np.linspace(100.0, 110.0, n),
        }
    )
    p = momentum_top_k_predictions(price, return_window=10, lookback=40, top_quantile=0.3, rebalance_every=3)
    assert set(p["signal"].unique()) <= {"Hold", "Buy"}


def test_mean_reversion_volume_sets_buy_after_trigger() -> None:
    # Need >= ret_lookback (min 20) history so rolling tail quantile is defined.
    n = 45
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = np.full(n, 100.0)
    crash_i = 28
    close[crash_i] = 92.0
    vol = np.full(n, 1_000_000.0)
    vol[crash_i - 1 : crash_i + 2] = 8_000_000.0
    ohlcv = pd.DataFrame({"date": dates, "close": close, "volume": vol.astype(int)})
    p = mean_reversion_volume_predictions(ohlcv, vol_lookback=5, ret_lookback=20, hold_days=2)
    assert (p["signal"] == "Buy").any()


def test_baseline_predictions_for_dispatches() -> None:
    price = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [1.0, 2.0],
        }
    )
    assert len(baseline_predictions_for("baseline_buy_hold", price)) == 2
    with pytest.raises(ValueError):
        baseline_predictions_for("unknown", price)
