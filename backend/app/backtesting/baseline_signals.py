"""Rule-based prediction series for long-only backtests (no ML artifact)."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical ids (also accept legacy baseline_* where noted)
RULE_BACKTEST_IDS: frozenset[str] = frozenset(
    {
        "buy_and_hold",
        "baseline_buy_hold",  # legacy alias → same as buy_and_hold
        "momentum_top_k",
        "mean_reversion_volume",
        "trend_filter",
        "baseline_ma_200",
    }
)

# For docs / suite ordering (canonical names only)
CANONICAL_RULE_STRATEGY_IDS: tuple[str, ...] = (
    "buy_and_hold",
    "momentum_top_k",
    "mean_reversion_volume",
    "trend_filter",
    "baseline_ma_200",
)

# Backward compat name used in older code paths
BACKTEST_BASELINE_IDS = RULE_BACKTEST_IDS


def is_rule_backtest_strategy(model: str) -> bool:
    return str(model).strip().lower() in RULE_BACKTEST_IDS


def is_baseline_strategy(model: str) -> bool:
    """Deprecated name: same as :func:`is_rule_backtest_strategy`."""
    return is_rule_backtest_strategy(model)


def buy_hold_predictions(price_df: pd.DataFrame) -> pd.DataFrame:
    """Always fully invested (Strong Buy) on every bar with a price."""
    p = price_df[["date"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    p["signal"] = "Strong Buy"
    p["probability"] = 1.0
    return (
        p.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    )


def ma_trend_predictions(price_df: pd.DataFrame, *, window: int = 200) -> pd.DataFrame:
    """
    Long when close > trailing SMA(window), else flat (Hold).

    Signal on day t affects return from t−1→t (engine uses position.shift(1)).
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
    p["probability"] = long_mask.astype(float)
    return p[["date", "signal", "probability"]]


def momentum_top_k_predictions(
    price_df: pd.DataFrame,
    *,
    return_window: int = 60,
    lookback: int = 252,
    top_quantile: float = 0.2,
    rebalance_every: int = 5,
) -> pd.DataFrame:
    """
    Single-name momentum filter: long when trailing ``return_window`` return is in the
    top ``top_quantile`` of its own rolling distribution (``lookback`` days), and positive.

    Rebalance decision is updated every ``rebalance_every`` bars (~weekly on dailies).
    This is not a multi-stock cross-section; it is an explainable single-asset analogue.
    """
    top_q = float(min(0.49, max(0.05, top_quantile)))
    rw = max(5, int(return_window))
    lb = max(rw + 10, int(lookback))
    step = max(1, int(rebalance_every))

    p = price_df[["date", "close"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    close = pd.to_numeric(p["close"], errors="coerce")
    r = close.pct_change(rw)
    thr = r.rolling(lb, min_periods=rw + 5).quantile(1.0 - top_q)
    raw_long = (r > 0) & (r >= thr)

    n = len(p)
    out_long: list[bool] = []
    last = False
    for i in range(n):
        if i % step == 0 or i == n - 1:
            v = raw_long.iloc[i]
            if pd.notna(v):
                last = bool(v)
        out_long.append(last)

    long_mask = pd.Series(out_long, index=p.index)
    p["signal"] = "Hold"
    p.loc[long_mask, "signal"] = "Buy"
    p["probability"] = long_mask.astype(float)
    return p[["date", "signal", "probability"]]


def mean_reversion_volume_predictions(
    ohlcv_df: pd.DataFrame,
    *,
    vol_lookback: int = 20,
    ret_lookback: int = 60,
    vol_mult: float = 2.0,
    ret_tail_q: float = 0.05,
    hold_days: int = 3,
) -> pd.DataFrame:
    """
    After a large down day with abnormally high volume vs rolling median, go **Buy**
    for the next ``hold_days`` sessions (short-term bounce hypothesis). Otherwise Hold.
    """
    vl = max(5, int(vol_lookback))
    rl = max(20, int(ret_lookback))
    hd = max(1, min(10, int(hold_days)))

    p = ohlcv_df[["date", "close"]].copy()
    p["date"] = pd.to_datetime(p["date"])
    if "volume" in ohlcv_df.columns:
        p["volume"] = pd.to_numeric(ohlcv_df["volume"], errors="coerce").fillna(0.0)
    else:
        p["volume"] = 0.0
    p = p.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    close = pd.to_numeric(p["close"], errors="coerce")
    vol = p["volume"].astype(float)
    ret = close.pct_change()
    vol_med = vol.rolling(vl, min_periods=5).median()
    vol_ok = vol_med > 0
    spike = vol_ok & (vol > float(vol_mult) * vol_med)
    tail = ret < ret.rolling(rl, min_periods=20).quantile(float(ret_tail_q))
    trigger = spike & tail & ret.notna()

    signals = np.array(["Hold"] * len(p), dtype=object)
    trig_idx = np.flatnonzero(trigger.to_numpy())
    for i in trig_idx:
        for j in range(1, hd + 1):
            k = i + j
            if k < len(signals):
                signals[k] = "Buy"
    p["signal"] = signals
    p["probability"] = (p["signal"] == "Buy").astype(float)
    return p[["date", "signal", "probability"]]


def rule_strategy_predictions(model: str, ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """Build (date, signal, probability) for a registered rule strategy id."""
    key = str(model).strip().lower()
    if key in ("buy_and_hold", "baseline_buy_hold"):
        return buy_hold_predictions(ohlcv_df)
    if key == "momentum_top_k":
        return momentum_top_k_predictions(ohlcv_df)
    if key == "mean_reversion_volume":
        return mean_reversion_volume_predictions(ohlcv_df)
    if key == "trend_filter":
        return ma_trend_predictions(ohlcv_df, window=50)
    if key == "baseline_ma_200":
        return ma_trend_predictions(ohlcv_df, window=200)
    raise ValueError(f"unknown rule strategy: {model!r}")


def baseline_predictions_for(model: str, ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible name for :func:`rule_strategy_predictions`."""
    return rule_strategy_predictions(model, ohlcv_df)


def suite_strategy_label(strategy_id: str) -> str:
    labels = {
        "buy_and_hold": "Buy & hold (benchmark)",
        "baseline_buy_hold": "Buy & hold (legacy id)",
        "momentum_top_k": "Momentum (60d vs own history, ~weekly)",
        "mean_reversion_volume": "Mean reversion (volume spike + tail return)",
        "trend_filter": "Trend filter (close > SMA50)",
        "baseline_ma_200": "Trend filter (close > SMA200)",
    }
    return labels.get(strategy_id.strip().lower(), strategy_id)
