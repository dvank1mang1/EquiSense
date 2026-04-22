from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.features.feature_store import FeatureStore
from app.jobs.run_ids import new_run_id
from app.ml.evaluation import financial_selection_metrics, information_coefficient_metrics
from app.research_models.dataset import build_research_panel, split_panel_by_date
from app.research_models.diagnostics import run_diagnostics
from app.research_models.models import classification_aux_metrics, train_research_model
from app.research_models.strategies import run_rank_based_strategy


@dataclass
class ResearchConfig:
    tickers: list[str]
    research_mode: bool
    model_type: str = "classification"
    strategy_type: str = "top_k"
    top_k_pct: float = 0.2
    threshold: float = 0.55
    rebalance_every: str = "daily"
    hold_days: int = 5
    score_normalization: bool = True
    max_turnover: float | None = None
    output_dir: str = "research_outputs"


@dataclass
class ResearchRunResult:
    config: dict[str, Any]
    metrics: dict[str, float]
    strategy_metrics: dict[str, float]
    diagnostics: dict[str, float | bool]
    output_dir: str


def _sanitize_metrics(raw: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def run_research_experiment(cfg: ResearchConfig) -> ResearchRunResult:
    if not cfg.research_mode:
        raise ValueError(
            "research_mode=False: add --research_mode to confirm optional experimental layer run"
        )
    if not cfg.tickers:
        raise ValueError("tickers list is empty")

    store = FeatureStore()
    ds = build_research_panel(store, cfg.tickers)
    train_df, _, test_df = split_panel_by_date(ds.panel)

    trained = train_research_model(
        model_type=cfg.model_type,
        train_df=train_df,
        feature_columns=ds.feature_columns,
    )
    test_scored = test_df.copy()
    test_scored["score"] = trained.predict_score(test_scored, ds.feature_columns)

    base_eval = pd.DataFrame(
        {
            "date": test_scored["date"],
            "score": test_scored["score"],
            "forward_return": test_scored["fwd_5d"],
            "target_cls": test_scored["target_cls"],
        }
    )
    metrics = {
        **_sanitize_metrics(
            information_coefficient_metrics(
                base_eval,
                score_col="score",
                return_col="forward_return",
                date_col="date",
                include_negated_score=True,
            )
        ),
        **_sanitize_metrics(
            financial_selection_metrics(
                base_eval,
                score_col="score",
                return_col="forward_return",
                date_col="date",
                top_q=max(0.05, min(cfg.top_k_pct, 0.4)),
                bottom_q=max(0.05, min(cfg.top_k_pct, 0.4)),
                label_return_threshold=0.0,
            )
        ),
    }
    metrics.update(
        _sanitize_metrics(classification_aux_metrics(test_scored["target_cls"], test_scored["score"]))
    )

    strat = run_rank_based_strategy(
        test_scored,
        strategy_type=cfg.strategy_type,
        top_k_pct=cfg.top_k_pct,
        threshold=cfg.threshold,
        rebalance_every=cfg.rebalance_every,
        score_normalization=cfg.score_normalization,
        max_turnover=cfg.max_turnover,
        hold_days=cfg.hold_days,
    )

    stamp = new_run_id()
    root = Path(cfg.output_dir).resolve() / f"{cfg.model_type}_{cfg.strategy_type}_{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    strat.daily.to_csv(root / "strategy_daily.csv", index=False)
    test_scored[["date", "ticker", "score", "fwd_1d", "fwd_5d", "target_cls"]].to_csv(
        root / "predictions.csv", index=False
    )
    diag = run_diagnostics(test_scored, root)

    payload = {
        "config": asdict(cfg),
        "metrics": metrics,
        "strategy_metrics": _sanitize_metrics(strat.metrics),
        "diagnostics": diag.summary,
        "diagnostics_report": diag.report_path,
    }
    (root / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return ResearchRunResult(
        config=asdict(cfg),
        metrics=metrics,
        strategy_metrics=_sanitize_metrics(strat.metrics),
        diagnostics=diag.summary,
        output_dir=str(root),
    )
