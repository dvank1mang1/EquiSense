# Research Pack Summary (rigorous)

Generated from `backend/data/processed` with **walk-forward expanding CV**, **purged k-fold + embargo**,
**holdout test**, **transaction costs**, **Diebold–Mariano** on daily losses.

## Main task (single source of truth)
- Primary objective: **cross-sectional stock ranking for portfolio selection**.
- Classifiers are used as score generators; ranking/trading metrics are primary, AUC/F1 are secondary diagnostics.

See **`notebooks/LITERATURE_REVIEW.md`** for paper references (XGB/LightGBM/FinBERT/Optuna + validation/statistics).
See **`notebooks/RESEARCH_OUTPUTS.md`** for where every artifact is written.

## Class balance & modeling choices (this run)
- Logistic baselines: `class_weight=balanced`; RandomForest / meta / OOF RF: `class_weight=balanced` (aligned with production training helpers).
- Median imputation for all sklearn pipelines in this pack.

## Label distribution (next-day up), by time split
| split | n | n_positive | n_negative | frac_positive |
| --- | --- | --- | --- | --- |
| train | 13450 | 5154 | 8296 | 0.3832 |
| validation | 2880 | 1138 | 1742 | 0.3951 |
| test | 2590 | 1010 | 1580 | 0.3900 |

## Validation & leakage control
- Target: `target_up_5d` = (next-day return > 0); features at `t` do not use future prices beyond the
  engineered pipeline.
- Walk-forward expanding splits and purged k-fold reduce overlap between train and test in time.
- Threshold for strategy (`p >= 0.60`) chosen on **validation** only, **not** on holdout.

## Holdout metrics (best row by ROC-AUC)
- **random_forest_optuna**: roc_auc=0.5023, pr_auc=0.3974, brier=0.3110, f1=0.3686

## Cross-validation (mean ROC-AUC across folds)
- Walk-forward: **0.5066**
- Purged k-fold: **0.5058**
- Purged k-fold + horizon: **0.5064**
- CPCV (combinatorial purged, full features): **0.5088**

## Ablations (feature groups)
- `tech_only`: 21 features
- `tech_fund`: 26 features
- `full`: 31 features

## Backtest (holdout, equal-weight, costs 2.0 bps per side on turnover)
- Strategy equity (net): **0.935** vs buy-and-hold **3.672**
- Meta-gated strategy equity (net): **1.190**
- Relative uplift vs B&H: **-74.54%**
- Net Sharpe (ann.): **-2.641**
- Meta Net Sharpe (ann.): **6.869**
- Max DD (net): **-0.0691**

## Diebold–Mariano (strategy vs benchmark log-loss)
- DM stat: **2.3492**
- p-value (two-sided): **1.8814e-02**
- Meta DM stat: **7.6215**
- Meta p-value (two-sided): **2.5080e-14**

## SPA-lite (block bootstrap on daily excess vs buy&hold)
- Observed mean excess: **-0.009437**
- One-sided p-value (H1: mean > 0): **0.5650**

## Interpretation (auto-generated checklist)
- If **holdout ROC-AUC ≈ 0.5** and CV means are near 0.5, treat directional signal as **not demonstrated** on this panel; focus on pipeline sanity, not live trading.
- **Brier** scores probability calibration (lower is better; random coin ≈ 0.25 for balanced binary). **PR-AUC** highlights precision–recall tradeoff when classes are skewed or costs asymmetric.
- Use **DM p-values** as a sanity check on forecast loss vs naive 0.5; they do not guarantee economic value after costs.
- **SPA-lite** is a coarse block-bootstrap on mean excess; it is **not** full Hansen (2005) SPA across many models — see literature notes.
- Compare **net** backtest curves to gross when costs matter; meta-gated curve is exploratory (OOF primary + meta on train/val).

## Produced artifacts
- `RESEARCH_SUMMARY.md` (this file), `label_distribution.csv`
- `cv_fold_metrics.csv`, `cv_summary.csv`
- `model_metrics.csv`, `test_predictions.csv`, `feature_importance_top20.csv`
- `backtest_curves.csv`, `backtest_curves_meta.csv`, `backtest_stats.csv`, `spa_lite_holdout.csv`
- PNGs `01`–`08` (see folder)
