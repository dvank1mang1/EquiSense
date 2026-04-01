"""Extended evaluation metrics for ranking and financial selection."""

from __future__ import annotations

import numpy as np
import pandas as pd


def precision_recall_at_k(
    y_true: pd.Series | np.ndarray,
    y_score: pd.Series | np.ndarray,
    *,
    k: int,
) -> dict[str, float]:
    yt = np.asarray(y_true).astype(int)
    ys = np.asarray(y_score).astype(float)
    if len(yt) == 0:
        return {"precision_at_k": float("nan"), "recall_at_k": float("nan")}
    k_eff = max(1, min(int(k), len(yt)))
    idx = np.argsort(-ys)[:k_eff]
    hits = int(yt[idx].sum())
    positives = int(yt.sum())
    precision = hits / k_eff
    recall = (hits / positives) if positives > 0 else float("nan")
    return {"precision_at_k": float(precision), "recall_at_k": float(recall)}


def financial_selection_metrics(
    frame: pd.DataFrame,
    *,
    score_col: str = "score",
    return_col: str = "forward_return",
    date_col: str = "date",
    top_q: float = 0.2,
    bottom_q: float = 0.2,
) -> dict[str, float]:
    if frame.empty:
        return {}
    d = frame[[date_col, score_col, return_col]].dropna().copy()
    if d.empty:
        return {}
    top_returns: list[float] = []
    bottom_returns: list[float] = []
    hit_rates: list[float] = []
    for _, g in d.groupby(date_col):
        g = g.sort_values(score_col, ascending=False)
        n = len(g)
        k_top = max(1, int(np.ceil(n * top_q)))
        k_bottom = max(1, int(np.ceil(n * bottom_q)))
        top = g.iloc[:k_top][return_col]
        bottom = g.iloc[-k_bottom:][return_col]
        top_returns.append(float(top.mean()))
        bottom_returns.append(float(bottom.mean()))
        hit_rates.append(float((top > 0.0).mean()))
    top_mean = float(np.mean(top_returns)) if top_returns else float("nan")
    bottom_mean = float(np.mean(bottom_returns)) if bottom_returns else float("nan")
    spread = top_mean - bottom_mean
    return {
        "top_quantile_return": top_mean,
        "bottom_quantile_return": bottom_mean,
        "long_short_spread": float(spread),
        "hit_rate_top_quantile": float(np.mean(hit_rates)) if hit_rates else float("nan"),
    }


def information_coefficient_metrics(
    frame: pd.DataFrame,
    *,
    score_col: str = "score",
    return_col: str = "forward_return",
    date_col: str = "date",
) -> dict[str, float]:
    d = frame[[date_col, score_col, return_col]].dropna().copy()
    if d.empty:
        return {}
    ic_vals: list[float] = []
    rank_ic_vals: list[float] = []
    for _, g in d.groupby(date_col):
        if len(g) < 3:
            continue
        ic = g[score_col].corr(g[return_col], method="pearson")
        ric = g[score_col].corr(g[return_col], method="spearman")
        if pd.notna(ic):
            ic_vals.append(float(ic))
        if pd.notna(ric):
            rank_ic_vals.append(float(ric))
    return {
        "ic_mean": float(np.mean(ic_vals)) if ic_vals else float("nan"),
        "rank_ic_mean": float(np.mean(rank_ic_vals)) if rank_ic_vals else float("nan"),
    }


def reliability_curve_and_ece(
    y_true: pd.Series | np.ndarray,
    y_score: pd.Series | np.ndarray,
    *,
    n_bins: int = 10,
) -> tuple[pd.DataFrame, float]:
    yt = np.asarray(y_true).astype(int)
    ys = np.asarray(y_score).astype(float)
    if len(yt) == 0:
        return pd.DataFrame(columns=["bin", "pred_mean", "obs_freq", "count"]), float("nan")
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ids = np.digitize(ys, bins[1:-1], right=False)
    rows: list[dict[str, float | int]] = []
    ece = 0.0
    n = len(yt)
    for i in range(n_bins):
        m = ids == i
        c = int(m.sum())
        if c == 0:
            rows.append({"bin": i, "pred_mean": np.nan, "obs_freq": np.nan, "count": 0})
            continue
        pred_mean = float(np.mean(ys[m]))
        obs = float(np.mean(yt[m]))
        ece += (c / n) * abs(obs - pred_mean)
        rows.append({"bin": i, "pred_mean": pred_mean, "obs_freq": obs, "count": c})
    return pd.DataFrame(rows), float(ece)
