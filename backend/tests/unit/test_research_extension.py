from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.research_models.diagnostics import run_diagnostics
from app.research_models.models import classification_aux_metrics
from app.research_models.strategies import run_rank_based_strategy


def _panel(n_dates: int = 30, n_tickers: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="D")
    rows: list[dict[str, object]] = []
    tickers = [f"T{i}" for i in range(n_tickers)]
    for di, dt in enumerate(dates):
        for ti, t in enumerate(tickers):
            score = float(ti) + 0.01 * di
            fwd5 = 0.02 * (ti - (n_tickers / 2)) + 0.001 * np.sin(di)
            rows.append(
                {
                    "date": dt,
                    "ticker": t,
                    "score": score,
                    "returns": 0.001 * (ti + 1),
                    "fwd_5d": fwd5,
                    "target_cls": int(fwd5 > 0.0),
                    "regime_high_vol": int(di % 2 == 0),
                    "regime_trend": int(ti % 2 == 0),
                }
            )
    return pd.DataFrame(rows)


def test_top_k_strategy_outputs_equity_curve_and_metrics() -> None:
    panel = _panel()
    out = run_rank_based_strategy(
        panel,
        strategy_type="top_k",
        top_k_pct=0.4,
        rebalance_every="weekly",
        score_normalization=True,
        max_turnover=0.5,
    )
    assert not out.daily.empty
    assert {"date", "portfolio_ret", "equity", "turnover"}.issubset(out.daily.columns)
    assert "sharpe" in out.metrics
    assert np.isfinite(float(out.metrics["turnover"]))


def test_hold_5d_strategy_runs_with_overlaps() -> None:
    panel = _panel(n_dates=40, n_tickers=6)
    out = run_rank_based_strategy(panel, strategy_type="hold_5d", top_k_pct=0.3, hold_days=5)
    assert len(out.daily) > 10
    assert float(out.daily["equity"].iloc[-1]) > 0.0


def test_diagnostics_writes_report(tmp_path: Path) -> None:
    panel = _panel()
    diag = run_diagnostics(panel, tmp_path)
    assert Path(diag.report_path).is_file()
    assert (tmp_path / "decile_table.csv").is_file()
    assert "monotonic_top_gt_bottom" in diag.summary


def test_classification_aux_metrics_has_prevalence_baseline() -> None:
    y = pd.Series([0, 0, 1, 0, 1, 1, 0, 1])
    s = pd.Series([0.1, 0.2, 0.9, 0.4, 0.7, 0.8, 0.3, 0.6])
    m = classification_aux_metrics(y, s)
    assert "pr_auc_vs_baseline" in m
