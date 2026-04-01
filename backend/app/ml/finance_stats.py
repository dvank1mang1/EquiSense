"""Finance-oriented statistics (Diebold–Mariano, Sharpe, drawdown, costs)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _normal_sf(x: float) -> float:
    """Survival function 1 - Phi(x) for standard normal (no scipy)."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def diebold_mariano(
    loss_a: np.ndarray,
    loss_b: np.ndarray,
    *,
    h: int = 1,
) -> dict[str, Any]:
    """
    Diebold–Mariano test for equal predictive accuracy (H0: E[d]=0, d = L_a - L_b).

    Uses Newey–West style correction for h-1 autocorrelation (simple Bartlett weights).
    For h=1, reduces to standard HAC with one lag.

    Returns dict with dm_stat, p_value_two_sided, mean_d.
    """
    a = np.asarray(loss_a, dtype=float).ravel()
    b = np.asarray(loss_b, dtype=float).ravel()
    if a.shape != b.shape:
        raise ValueError("loss_a and loss_b must have equal shape")
    finite = np.isfinite(a) & np.isfinite(b)
    a = a[finite]
    b = b[finite]
    if len(a) < 5:
        raise ValueError("loss_a and loss_b must have at least 5 finite observations")
    d = a - b
    n = len(d)
    d_bar = float(np.mean(d))

    # Newey–West variance of mean(d)
    gamma0 = float(np.mean((d - d_bar) ** 2))
    var = gamma0 / n
    h_eff = min(h, n - 1)
    for lag in range(1, h_eff + 1):
        w = 1.0 - lag / (h_eff + 1)  # Bartlett
        cov = float(np.mean((d[lag:] - d_bar) * (d[:-lag] - d_bar)))
        var += 2.0 * w * cov / n

    if var <= 0 or not math.isfinite(var):
        return {"dm_stat": 0.0, "p_value_two_sided": 1.0, "mean_d": d_bar, "var_mean_d": 0.0}

    se = math.sqrt(var)
    dm_stat = d_bar / se if se > 0 else 0.0
    p_two = 2.0 * min(_normal_sf(abs(dm_stat)), 0.999999999)
    return {
        "dm_stat": float(dm_stat),
        "p_value_two_sided": float(p_two),
        "mean_d": d_bar,
        "var_mean_d": float(var),
    }


def annualized_sharpe(daily_returns: np.ndarray, *, trading_days: int = 252) -> float:
    r = np.asarray(daily_returns, dtype=float).ravel()
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return float("nan")
    return (mu / sd) * math.sqrt(trading_days)


def max_drawdown(equity_curve: np.ndarray) -> float:
    """Max drawdown given cumulative equity (e.g. cumprod of 1+r)."""
    eq = np.asarray(equity_curve, dtype=float).ravel()
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak) - 1.0
    return float(np.min(dd))


def net_returns_with_transaction_costs(
    gross_returns: np.ndarray,
    positions: np.ndarray,
    *,
    cost_per_turn: float,
) -> np.ndarray:
    """
    Subtract proportional transaction costs when position changes.

    cost_per_turn: fraction of capital per unit change in position (e.g. 0.0002 = 2 bps per side).
    """
    g = np.asarray(gross_returns, dtype=float).ravel()
    p = np.asarray(positions, dtype=float).ravel()
    if g.shape != p.shape:
        raise ValueError("gross_returns and positions must match")
    if cost_per_turn < 0:
        raise ValueError("cost_per_turn must be non-negative")
    # Start from flat position at t0, so entering a position incurs cost.
    dp = np.diff(p, prepend=0.0)
    cost = np.abs(dp) * cost_per_turn
    return g - cost  # type: ignore[no-any-return]
