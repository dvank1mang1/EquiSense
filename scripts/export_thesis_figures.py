#!/usr/bin/env python3
"""
Assemble thesis-ready figures and tables into ./thesis_figures/.

Reads latest outputs from notebooks/results/ (run run_research_pack.py first).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "notebooks" / "results"
OUT = ROOT / "thesis_figures"


def _copy_if_exists(name: str) -> None:
    src = SRC / name
    if not src.is_file():
        raise FileNotFoundError(f"Missing source file: {src}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(src.read_bytes())


def _copy_alias(src_name: str, dest_name: str) -> None:
    """Same image under a LaTeX-friendly filename (e.g. quantile_plot.png)."""
    src = SRC / src_name
    if not src.is_file():
        raise FileNotFoundError(f"Missing source file: {src}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / dest_name).write_bytes(src.read_bytes())


def _build_strategy_table_md() -> None:
    clean = pd.read_csv(OUT / "strategy_comparison_clean.csv")
    # Readable numeric formatting for thesis paste-in
    hdr = (
        "| Strategy | IC | Precision@k | Sharpe | Avg. return | Hit rate |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    )
    body_lines: list[str] = []
    for _, r in clean.iterrows():
        ic = float(r["ic"])
        ic_s = f"{ic:.4f}" if abs(ic) >= 1e-3 else f"{ic:.2e}"
        name = str(r["strategy"]).replace("_", " ")
        body_lines.append(
            f"| {name} | {ic_s} | {float(r['precision_at_k']):.4f} | "
            f"{float(r['sharpe']):.4f} | {float(r['average_return']):.6f} | "
            f"{float(r['hit_rate']):.4f} |"
        )
    md_lines = [
        "# Strategy comparison (holdout, cross-sectional ranking)",
        "",
        "Values from `strategy_comparison_clean.csv` (research pipeline).",
        "",
        hdr + "\n".join(body_lines),
        "",
    ]
    (OUT / "strategy_comparison_table.md").write_text("\n".join(md_lines), encoding="utf-8")


def _build_long_short_cumulative() -> None:
    """
    Per-date long–short: top prediction quantile minus bottom (Q5 − Q1),
    same cross-sectional bins as cumulative_returns_by_quantile.
    """
    daily = pd.read_csv(SRC / "quantile_daily_returns.csv")
    if daily.empty:
        raise ValueError("quantile_daily_returns.csv is empty")
    daily["date"] = pd.to_datetime(daily["date"])
    pivot = daily.pivot(index="date", columns="quantile", values="mean_return").sort_index()
    if 1 not in pivot.columns or pivot.columns.max() < 2:
        raise ValueError("Need quantiles 1 and max for long–short")
    top_q = int(pivot.columns.max())
    bot_q = 1
    ls = pivot[top_q] - pivot[bot_q]
    ls.name = "long_short_daily"
    out_daily = ls.reset_index()
    out_daily.to_csv(OUT / "long_short_daily_returns.csv", index=False)
    cum = (1.0 + ls.fillna(0.0)).cumprod()
    cum_df = cum.reset_index()
    cum_df.columns = ["date", "long_short_cumulative"]
    cum_df.to_csv(OUT / "long_short_cumulative_returns.csv", index=False)

    plt.figure(figsize=(12, 6))
    plt.plot(cum_df["date"], cum_df["long_short_cumulative"], color="#1f4e79", linewidth=2.0)
    plt.title("Cumulative Long–Short Return (Top vs. Bottom Prediction Quantile)")
    plt.xlabel("Date")
    plt.ylabel("Cumulative return (1 + daily spread).cumprod()")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT / "long_short_cumulative.png", dpi=170)
    plt.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (
        "quantile_returns.png",
        "cumulative_returns_by_quantile.png",
        "sharpe_comparison.png",
        "ic_vs_precision.png",
        "strategy_comparison_clean.csv",
    ):
        _copy_if_exists(name)
    # Names expected by typical thesis LaTeX \includegraphics{...}
    _copy_alias("quantile_returns.png", "quantile_plot.png")
    _copy_alias("cumulative_returns_by_quantile.png", "cum_returns.png")
    _build_strategy_table_md()
    _build_long_short_cumulative()
    print(f"Thesis figures ready in: {OUT}")


if __name__ == "__main__":
    main()
