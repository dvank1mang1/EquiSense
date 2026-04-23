from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.ml.evaluation import information_coefficient_metrics


@dataclass
class DiagnosticsResult:
    summary: dict[str, float | bool]
    decile_table: pd.DataFrame
    regime_table: pd.DataFrame
    report_path: str


def _safe_float(v: float) -> float:
    return float(v) if np.isfinite(v) else float("nan")


def _decile_table(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame[["date", "score", "fwd_5d", "target_cls"]].dropna().copy()
    if d.empty:
        return pd.DataFrame(columns=["decile", "mean_fwd_5d", "median_fwd_5d", "hit_rate", "count"])
    d["decile"] = (
        d.groupby("date")["score"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False, duplicates="drop"))
        .astype(float)
    )
    out = (
        d.dropna(subset=["decile"])
        .groupby("decile")
        .agg(
            mean_fwd_5d=("fwd_5d", "mean"),
            median_fwd_5d=("fwd_5d", "median"),
            hit_rate=("target_cls", "mean"),
            count=("fwd_5d", "size"),
        )
        .reset_index()
    )
    out["decile"] = out["decile"].astype(int)
    return out.sort_values("decile").reset_index(drop=True)


def _regime_ic_table(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame[["date", "score", "fwd_5d", "regime_high_vol", "regime_trend"]].dropna().copy()
    if d.empty:
        return pd.DataFrame(columns=["regime", "ic_mean", "rank_ic_mean", "n_rows"])

    def _ic_for(mask: pd.Series, name: str) -> dict[str, float | str]:
        g = d.loc[mask].copy()
        m = information_coefficient_metrics(
            g.rename(columns={"fwd_5d": "forward_return"}),
            score_col="score",
            return_col="forward_return",
            date_col="date",
        )
        return {
            "regime": name,
            "ic_mean": _safe_float(float(m.get("ic_mean", np.nan))),
            "rank_ic_mean": _safe_float(float(m.get("rank_ic_mean", np.nan))),
            "n_rows": float(len(g)),
        }

    rows = [
        _ic_for(d["regime_high_vol"] == 1, "high_vol"),
        _ic_for(d["regime_high_vol"] == 0, "low_vol"),
        _ic_for(d["regime_trend"] == 1, "trend"),
        _ic_for(d["regime_trend"] == 0, "non_trend"),
    ]
    return pd.DataFrame(rows)


def _save_decile_plot(decile: pd.DataFrame, out_dir: Path) -> None:
    if decile.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(decile["decile"], decile["mean_fwd_5d"], marker="o")
    ax.set_title("Score Decile vs Mean fwd_5d")
    ax.set_xlabel("Decile (0=lowest score, 9=highest score)")
    ax.set_ylabel("Mean fwd_5d")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "decile_mean_fwd5d.png", dpi=140)
    plt.close(fig)


def run_diagnostics(frame: pd.DataFrame, out_dir: Path) -> DiagnosticsResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    dec = _decile_table(frame)
    reg = _regime_ic_table(frame)
    dec_path = out_dir / "decile_table.csv"
    reg_path = out_dir / "regime_ic.csv"
    dec.to_csv(dec_path, index=False)
    reg.to_csv(reg_path, index=False)
    _save_decile_plot(dec, out_dir)

    ic = information_coefficient_metrics(
        frame.rename(columns={"fwd_5d": "forward_return"}),
        score_col="score",
        return_col="forward_return",
        date_col="date",
        include_negated_score=True,
    )
    top = dec[dec["decile"] == dec["decile"].max()] if not dec.empty else pd.DataFrame()
    bot = dec[dec["decile"] == dec["decile"].min()] if not dec.empty else pd.DataFrame()
    top_mean = float(top["mean_fwd_5d"].iloc[0]) if not top.empty else float("nan")
    bot_mean = float(bot["mean_fwd_5d"].iloc[0]) if not bot.empty else float("nan")
    monotonic_ok = bool(np.isfinite(top_mean) and np.isfinite(bot_mean) and top_mean > bot_mean)
    signal_inverted = bool(
        np.isfinite(float(ic.get("ic_mean", np.nan)))
        and np.isfinite(float(ic.get("ic_mean_neg_score", np.nan)))
        and float(ic["ic_mean_neg_score"]) > float(ic["ic_mean"])
    )
    summary: dict[str, float | bool] = {
        "top_decile_mean_fwd_5d": _safe_float(top_mean),
        "bottom_decile_mean_fwd_5d": _safe_float(bot_mean),
        "monotonic_top_gt_bottom": monotonic_ok,
        "signal_looks_inverted": signal_inverted,
        "ic_mean": _safe_float(float(ic.get("ic_mean", np.nan))),
        "rank_ic_mean": _safe_float(float(ic.get("rank_ic_mean", np.nan))),
        "ic_mean_neg_score": _safe_float(float(ic.get("ic_mean_neg_score", np.nan))),
        "rank_ic_mean_neg_score": _safe_float(float(ic.get("rank_ic_mean_neg_score", np.nan))),
    }

    report_path = out_dir / "diagnostics_summary.md"
    lines = [
        "# Research diagnostics",
        "",
        f"- Top decile mean fwd_5d: {summary['top_decile_mean_fwd_5d']:.6f}",
        f"- Bottom decile mean fwd_5d: {summary['bottom_decile_mean_fwd_5d']:.6f}",
        f"- Monotonic top > bottom: {summary['monotonic_top_gt_bottom']}",
        f"- Signal inverted check: {summary['signal_looks_inverted']}",
        f"- IC mean: {summary['ic_mean']:.6f}",
        f"- Rank IC mean: {summary['rank_ic_mean']:.6f}",
        f"- IC mean (-score): {summary['ic_mean_neg_score']:.6f}",
        f"- Rank IC mean (-score): {summary['rank_ic_mean_neg_score']:.6f}",
        "",
        "Artifacts:",
        f"- {dec_path.name}",
        f"- {reg_path.name}",
        "- decile_mean_fwd5d.png",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return DiagnosticsResult(
        summary=summary,
        decile_table=dec,
        regime_table=reg,
        report_path=str(report_path),
    )
