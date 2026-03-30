"""Research utilities: time-aware CV, finance stats, backtest helpers."""

from app.ml.cv import (
    combinatorial_purged_cv_splits,
    mask_for_dates,
    purged_kfold_splits,
    purged_kfold_with_horizon,
    walk_forward_expanding_splits,
)
from app.ml.finance_stats import (
    annualized_sharpe,
    diebold_mariano,
    max_drawdown,
    net_returns_with_transaction_costs,
)
from app.ml.meta_labeling import apply_meta_gating, build_meta_labels, fit_meta_model
from app.ml.oof import oof_primary_proba
from app.ml.spa_lite import block_bootstrap_mean_pvalue

__all__ = [
    "annualized_sharpe",
    "diebold_mariano",
    "max_drawdown",
    "net_returns_with_transaction_costs",
    "mask_for_dates",
    "purged_kfold_splits",
    "purged_kfold_with_horizon",
    "walk_forward_expanding_splits",
    "combinatorial_purged_cv_splits",
    "oof_primary_proba",
    "block_bootstrap_mean_pvalue",
    "build_meta_labels",
    "fit_meta_model",
    "apply_meta_gating",
]
