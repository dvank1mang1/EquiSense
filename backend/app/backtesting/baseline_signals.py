"""Rule-based prediction series for long-only backtests (no ML artifact)."""

from __future__ import annotations

import pandas as pd


def buy_hold_predictions(price_df: pd.DataFrame) -> pd.DataFrame:
    """Always fully invested (Strong Buy) on every bar with a price."""
    p = price_df[["date"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    p["signal"] = "Strong Buy"
    p["probability"] = 1.0
    return p.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def ma_trend_predictions(price_df: pd.DataFrame, *, window: int = 200) -> pd.DataFrame:
    """
    Long when close > trailing SMA(window), else flat (Hold).

    Uses the same bar for signal as the engine applies with shift(1): signal on day t
    affects return from t-1→t, so MA is computed on close including day t (no future close).
    """
    w = max(2, int(window))
    p = price_df[["date", "close"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    close = pd.to_numeric(p["close"], errors="coerce")
    ma = close.rolling(window=w, min_periods=w).mean()
    long_mask = close > ma
    p["signal"] = "Hold"
    p.loc[long_mask, "signal"] = "Buy"
    # Pseudo-probability for API parity: 1 in long regime, 0 flat
    p["probability"] = long_mask.astype(float)
    return p[["date", "signal", "probability"]]


BACKTEST_BASELINE_IDS: frozenset[str] = frozenset({"baseline_buy_hold", "baseline_ma_200"})


def is_baseline_strategy(model: str) -> bool:
    return model.strip().lower() in BACKTEST_BASELINE_IDS


def baseline_predictions_for(model: str, price_df: pd.DataFrame) -> pd.DataFrame:
    key = model.strip().lower()
    if key == "baseline_buy_hold":
        return buy_hold_predictions(price_df)
    if key == "baseline_ma_200":
        return ma_trend_predictions(price_df, window=200)
    raise ValueError(f"unknown baseline strategy: {model!r}")
