# Research Pack Summary (rigorous)

Generated from `backend/data/processed` with **walk-forward expanding CV**, **purged k-fold + embargo**,
**holdout test**, **transaction costs**, **Diebold–Mariano** on daily losses.

See **`notebooks/LITERATURE_REVIEW.md`** for paper references (XGB/LightGBM/FinBERT/Optuna + validation/statistics).
See **`notebooks/RESEARCH_OUTPUTS.md`** for where every artifact is written.

## Class balance & modeling choices (this run)
- Logistic baselines: `class_weight=balanced`; RandomForest / meta / OOF RF: `class_weight=balanced` (aligned with production training helpers).
- Median imputation for all sklearn pipelines in this pack.

## Label distribution (next-day up), by time split
| split | n | n_positive | n_negative | frac_positive |
| --- | --- | --- | --- | --- |
| train | 12780 | 6404 | 6376 | 0.5011 |
| validation | 2740 | 1382 | 1358 | 0.5044 |
| test | 2740 | 1395 | 1345 | 0.5091 |

## Validation & leakage control
- Target: `target_up_1d` = (next-day return > 0); features at `t` do not use future prices beyond the
  engineered pipeline.
- Walk-forward expanding splits and purged k-fold reduce overlap between train and test in time.
- Threshold for strategy (`p >= 0.45`) chosen on **validation** only, **not** on holdout.

## Holdout metrics (best row by ROC-AUC)
- **logreg_pca**: roc_auc=0.4844, f1=0.4634

## Cross-validation (mean ROC-AUC across folds)
- Walk-forward: **0.5015**
- Purged k-fold: **0.4981**
- Purged k-fold + horizon: **0.4966**
- CPCV (combinatorial purged, full features): **0.5003**

## Ablations (feature groups)
- `tech_only`: 21 features
- `tech_fund`: 26 features
- `full`: 31 features

## Backtest (holdout, equal-weight, costs 2.0 bps per side on turnover)
- Strategy equity (net): **1.126** vs buy-and-hold **1.184**
- Meta-gated strategy equity (net): **4.719**
- Relative uplift vs B&H: **-4.96%**
- Net Sharpe (ann.): **1.449**
- Meta Net Sharpe (ann.): **31.827**
- Max DD (net): **-0.0387**

## Diebold–Mariano (strategy vs benchmark log-loss)
- DM stat: **0.2282**
- p-value (two-sided): **8.1945e-01**
- Meta DM stat: **2.4555**
- Meta p-value (two-sided): **1.4070e-02**

## SPA-lite (block bootstrap on daily excess vs buy&hold)
- Observed mean excess: **-0.000186**
- One-sided p-value (H1: mean > 0): **0.5040**

## Interpretation (auto-generated checklist)
- If **holdout ROC-AUC ≈ 0.5** and CV means are near 0.5, treat directional signal as **not demonstrated** on this panel; focus on pipeline sanity, not live trading.
- Use **DM p-values** as a sanity check on forecast loss vs naive 0.5; they do not guarantee economic value after costs.
- **SPA-lite** is a coarse block-bootstrap on mean excess; it is **not** full Hansen (2005) SPA across many models — see literature notes.
- Compare **net** backtest curves to gross when costs matter; meta-gated curve is exploratory (OOF primary + meta on train/val).

## Produced artifacts
- `RESEARCH_SUMMARY.md` (this file), `label_distribution.csv`
- `cv_fold_metrics.csv`, `cv_summary.csv`
- `model_metrics.csv`, `test_predictions.csv`, `feature_importance_top20.csv`
- `backtest_curves.csv`, `backtest_curves_meta.csv`, `backtest_stats.csv`, `spa_lite_holdout.csv`
- PNGs `01`–`08` (see folder)
