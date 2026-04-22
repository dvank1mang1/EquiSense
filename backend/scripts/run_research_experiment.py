"""Optional research extension CLI (isolated from production training pipeline)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.research_models.runner import ResearchConfig, run_research_experiment


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run optional research models + strategies experiments")
    p.add_argument("--tickers", nargs="+", required=True, help="Universe tickers, e.g. AAPL MSFT NVDA")
    p.add_argument(
        "--research_mode",
        action="store_true",
        help="Safety flag: must be passed to run optional research layer",
    )
    p.add_argument(
        "--model_type",
        default="classification",
        choices=["classification", "regression", "ranking"],
        help="Research model type",
    )
    p.add_argument(
        "--strategy_type",
        default="top_k",
        choices=["threshold", "top_k", "hold_5d"],
        help="Execution strategy in research layer",
    )
    p.add_argument("--top_k_pct", type=float, default=0.2, help="Top-k fraction for rank strategy")
    p.add_argument("--threshold", type=float, default=0.55, help="Threshold strategy cut-off")
    p.add_argument(
        "--rebalance_every",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Rebalance frequency",
    )
    p.add_argument("--hold_days", type=int, default=5, help="Holding days for hold_5d strategy")
    p.add_argument(
        "--score_normalization",
        action="store_true",
        help="Normalize scores cross-sectionally by date before strategy",
    )
    p.add_argument(
        "--max_turnover",
        type=float,
        default=None,
        help="Optional turnover cap per rebalance step (L1 weight delta)",
    )
    p.add_argument(
        "--output_dir",
        default="research_outputs",
        help="Base directory for artifacts",
    )
    p.add_argument(
        "--compare_all",
        action="store_true",
        help="Run all model types with current strategy flags",
    )
    return p


def _single_config(args: argparse.Namespace, model_type: str) -> ResearchConfig:
    return ResearchConfig(
        tickers=[str(t).strip().upper() for t in args.tickers if str(t).strip()],
        research_mode=bool(args.research_mode),
        model_type=model_type,
        strategy_type=str(args.strategy_type),
        top_k_pct=float(args.top_k_pct),
        threshold=float(args.threshold),
        rebalance_every=str(args.rebalance_every),
        hold_days=int(args.hold_days),
        score_normalization=bool(args.score_normalization),
        max_turnover=float(args.max_turnover) if args.max_turnover is not None else None,
        output_dir=str(args.output_dir),
    )


def main() -> None:
    args = build_parser().parse_args()
    model_types = (
        ["classification", "regression", "ranking"] if args.compare_all else [str(args.model_type)]
    )
    runs = []
    for mt in model_types:
        cfg = _single_config(args, mt)
        run = run_research_experiment(cfg)
        runs.append(run)
        print(
            json.dumps(
                {
                    "model_type": mt,
                    "strategy_type": cfg.strategy_type,
                    "output_dir": run.output_dir,
                    "metrics": run.metrics,
                    "strategy_metrics": run.strategy_metrics,
                    "diagnostics": run.diagnostics,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )

    if len(runs) > 1:
        print("\n=== Comparison (model_type -> rank_ic_mean, long_short_spread, sharpe) ===")
        for r in runs:
            mt = str(r.config.get("model_type"))
            rank_ic = r.metrics.get("rank_ic_mean", float("nan"))
            spread = r.metrics.get("long_short_spread", float("nan"))
            sharpe = r.strategy_metrics.get("sharpe", float("nan"))
            print(f"{mt:>14} | rank_ic={rank_ic:.6f} | spread={spread:.6f} | sharpe={sharpe:.6f}")


if __name__ == "__main__":
    main()
