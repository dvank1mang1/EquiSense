from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StrategyResult:
    daily: pd.DataFrame
    metrics: dict[str, float]


def _normalize_scores_cross_section(frame: pd.DataFrame, score_col: str) -> pd.Series:
    def _z(g: pd.Series) -> pd.Series:
        mu = float(g.mean())
        sd = float(g.std(ddof=0))
        if sd <= 1e-12:
            return pd.Series(np.zeros(len(g)), index=g.index, dtype=float)
        return (g - mu) / sd

    return frame.groupby("date")[score_col].transform(_z)


def _compute_portfolio_metrics(daily: pd.DataFrame) -> dict[str, float]:
    rets = pd.to_numeric(daily["portfolio_ret"], errors="coerce").fillna(0.0)
    curve = (1.0 + rets).cumprod()
    sharpe = 0.0
    std = float(rets.std(ddof=0))
    if std > 1e-12:
        sharpe = float((rets.mean() / std) * np.sqrt(252.0))
    peak = curve.cummax()
    dd = (curve / peak) - 1.0
    return {
        "cumulative_return": float(curve.iloc[-1] - 1.0) if len(curve) else 0.0,
        "annualized_return": float(curve.iloc[-1] ** (252.0 / max(1, len(curve))) - 1.0)
        if len(curve)
        else 0.0,
        "sharpe": sharpe,
        "max_drawdown": float(dd.min()) if len(dd) else 0.0,
        "turnover": float(daily["turnover"].mean()) if "turnover" in daily.columns else 0.0,
    }


def _eligible_rebalance_dates(dates: list[pd.Timestamp], rebalance_every: str) -> set[pd.Timestamp]:
    r = rebalance_every.strip().lower()
    if r == "daily":
        return set(dates)
    if r == "weekly":
        return set(d for i, d in enumerate(dates) if i % 5 == 0)
    if r == "monthly":
        return set(d for i, d in enumerate(dates) if i % 21 == 0)
    raise ValueError("rebalance_every must be daily|weekly|monthly")


def _apply_turnover_cap(
    previous: pd.Series, target: pd.Series, *, max_turnover: float | None
) -> tuple[pd.Series, float]:
    prev = previous.reindex(target.index).fillna(0.0)
    desired = target.fillna(0.0)
    delta = desired - prev
    gross = float(np.abs(delta).sum())
    if max_turnover is None or max_turnover <= 0.0 or gross <= max_turnover:
        return desired, gross
    scale = float(max_turnover / max(gross, 1e-12))
    adjusted = prev + delta * scale
    return adjusted, float(np.abs(adjusted - prev).sum())


def _top_k_weights(scores: pd.Series, top_k_pct: float) -> pd.Series:
    n = len(scores)
    k = max(1, int(np.ceil(n * top_k_pct)))
    ranked = scores.sort_values(ascending=False)
    w = pd.Series(0.0, index=scores.index, dtype=float)
    sel = ranked.index[:k]
    w.loc[sel] = 1.0 / k
    return w


def _threshold_weights(scores: pd.Series, threshold: float) -> pd.Series:
    sel = scores[scores >= float(threshold)].index
    w = pd.Series(0.0, index=scores.index, dtype=float)
    if len(sel) == 0:
        return w
    w.loc[sel] = 1.0 / len(sel)
    return w


def run_rank_based_strategy(
    panel_with_score: pd.DataFrame,
    *,
    strategy_type: str,
    top_k_pct: float = 0.2,
    threshold: float = 0.55,
    rebalance_every: str = "daily",
    score_normalization: bool = False,
    max_turnover: float | None = None,
    hold_days: int = 5,
) -> StrategyResult:
    df = panel_with_score[["date", "ticker", "score", "returns"]].dropna().copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values(["date", "ticker"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("strategy input is empty")

    if score_normalization:
        df["score"] = _normalize_scores_cross_section(df, "score")

    dates = [pd.Timestamp(d) for d in np.sort(df["date"].unique())]
    rebal_dates = _eligible_rebalance_dates(dates, rebalance_every)
    tickers = sorted(df["ticker"].astype(str).unique())
    returns = (
        df.pivot_table(index="date", columns="ticker", values="returns", aggfunc="last")
        .reindex(index=dates, columns=tickers)
        .fillna(0.0)
    )
    scores = (
        df.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
        .reindex(index=dates, columns=tickers)
        .fillna(0.0)
    )

    mode = strategy_type.strip().lower()
    if mode in {"threshold", "top_k"}:
        target = pd.DataFrame(0.0, index=dates, columns=tickers, dtype=float)
        previous = pd.Series(0.0, index=tickers, dtype=float)
        for d in dates:
            if d in rebal_dates:
                s = scores.loc[d]
                want = (
                    _top_k_weights(s, top_k_pct)
                    if mode == "top_k"
                    else _threshold_weights(s, threshold)
                )
                chosen, _ = _apply_turnover_cap(previous, want, max_turnover=max_turnover)
                previous = chosen
            target.loc[d] = previous
        executed = target.shift(1).fillna(0.0)
    elif mode == "hold_5d":
        hd = max(1, int(hold_days))
        entries = pd.DataFrame(0.0, index=dates, columns=tickers, dtype=float)
        for d in dates:
            if d not in rebal_dates:
                continue
            s = scores.loc[d]
            entries.loc[d] = _top_k_weights(s, top_k_pct)
        executed = pd.DataFrame(0.0, index=dates, columns=tickers, dtype=float)
        for lag in range(1, hd + 1):
            executed += entries.shift(lag).fillna(0.0) / float(hd)
    else:
        raise ValueError("strategy_type must be threshold|top_k|hold_5d")

    port_ret = (executed * returns).sum(axis=1)
    turnover = executed.diff().abs().sum(axis=1).fillna(executed.abs().sum(axis=1))
    daily = pd.DataFrame(
        {
            "date": dates,
            "portfolio_ret": port_ret.values,
            "equity": (1.0 + port_ret).cumprod().values,
            "turnover": turnover.values,
        }
    )
    metrics = _compute_portfolio_metrics(daily)
    return StrategyResult(daily=daily, metrics=metrics)
