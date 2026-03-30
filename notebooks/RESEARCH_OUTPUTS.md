# Where research results land

Running:

```bash
cd backend && uv run python ../notebooks/run_research_pack.py
```

writes into **`notebooks/results/`** (repo root relative to command).

| Artifact | What it is |
|----------|------------|
| **`RESEARCH_SUMMARY.md`** | Human-readable conclusions: CV means, holdout metrics, backtest, DM, SPA-lite, **interpretation checklist**, pointers to literature. **Start here for “what did we conclude?”** |
| **`label_distribution.csv`** | Row counts and fraction of positive `target_up_1d` per time split (train / validation / test). |
| **`cv_fold_metrics.csv`** | Per-fold ROC-AUC / F1 by split type (walk-forward, purged k-fold, horizon, CPCV) and ablation. |
| **`cv_summary.csv`** | Aggregated mean/std of CV ROC-AUC by protocol. |
| **`model_metrics.csv`** | Holdout accuracy / F1 / ROC-AUC / **PR-AUC** / **Brier** for baseline, PCA+logreg, Optuna RF. |
| **`test_predictions.csv`** | Per-row test predictions + meta columns. |
| **`feature_importance_top20.csv`** | RF importances (top 20). |
| **`backtest_curves*.csv`** | Daily equity / signals for primary and meta strategies. |
| **`backtest_stats.csv`** | Sharpe, drawdown, DM stats, SPA fields, threshold. |
| **`spa_lite_holdout.csv`** | Block-bootstrap SPA-lite statistics. |
| **`01_*.png` … `08_*.png`** | EDA and result plots. |

Theory and paper mapping: **`notebooks/LITERATURE_REVIEW.md`**.

Production training (API) metrics live on training runs / experiment store, not in this folder.
