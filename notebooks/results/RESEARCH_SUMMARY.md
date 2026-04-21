# Research Pack Summary (rigorous)

Generated from `backend/data/processed` with **walk-forward expanding CV**, **purged k-fold + embargo**,
**holdout test**, **transaction costs**, and **Diebold–Mariano** on a **daily** universe-direction benchmark (see DM section).

## Main task (single source of truth)
- Primary objective: **cross-sectional stock ranking for portfolio selection**.
- Classifiers are used as score generators; ranking/trading metrics are primary.
- **ROC-AUC** and **PR-AUC** are reported in `model_metrics.csv` as **auxiliary classification** diagnostics; they are not optimization targets for Optuna in this pack.

See **`notebooks/LITERATURE_REVIEW.md`** for paper references (XGB/LightGBM/FinBERT/Optuna + validation/statistics).
See **`notebooks/RESEARCH_OUTPUTS.md`** for where every artifact is written.

## Class balance & modeling choices (this run)
- Logistic baselines: `class_weight=balanced`; RandomForest / meta / OOF RF: `class_weight=balanced` (aligned with production training helpers).
- Median imputation for all sklearn pipelines in this pack.

## Label distribution (5-day cumulative up > 1%), by time split
| split | n | n_positive | n_negative | frac_positive |
| --- | --- | --- | --- | --- |
| train | 13450 | 5154 | 8296 | 0.3832 |
| validation | 2880 | 1138 | 1742 | 0.3951 |
| test | 2590 | 1010 | 1580 | 0.3900 |

## Validation & leakage control
- Target: `target_up_5d` = 1 iff **5-day cumulative forward return** `fwd_5d` > **1%** (sum of next five daily returns from `t+1`); features at `t` do not use future prices beyond the engineered pipeline.
- **IC, Rank IC, precision@k, quantile / long–short spread** use the same horizon: `forward_return` in evaluation frames is **`fwd_5d`**, not next-day `ret_1d`.
- **Equal-weight backtests, DM, SPA-lite** use **daily** `ret_1d` (execution / reporting horizon); do not equate that PnL horizon with the 5-day label unless you redesign the strategy to hold 5 days.
- Walk-forward expanding splits and purged k-fold reduce overlap between train and test in time.
- Threshold for strategy (`p >= 0.58`) chosen on **validation** only, **not** on holdout.

## Holdout — classification (best row by Rank IC)
- **xgboost_optuna**: prevalence=0.3900, pr_auc=0.3939 (pr_auc − prevalence=0.0039), roc_auc=0.4984

## Holdout — ranking / 5d forward return (same horizon as label)
- **xgboost_optuna**: ic=0.0324, rank_ic=0.0379, precision@k (per-date top 20% by score)=0.3962, long_short_spread=0.038182
- Pooled-row precision (legacy, not comparable to IC) is in `model_metrics.csv` as `precision_at_k_pooled_top25pct_rows`.

## Cross-validation (mean Rank IC across folds)
- Walk-forward: **0.0119**
- Purged k-fold: **0.0094**
- Purged k-fold + horizon: **0.0060**
- CPCV (combinatorial purged, full features): **0.0095**

## Ablations (feature groups)
- `tech_only`: 21 features
- `tech_fund`: 26 features
- `full`: 31 features

## Backtest (holdout, equal-weight, costs 2.0 bps per side on turnover)
- Strategy equity (net): **0.887** vs buy-and-hold **3.672**
- Meta-gated strategy equity (net): **1.005**
- Relative uplift vs B&H: **-75.85%**
- Net Sharpe (ann.): **-2.484**
- Meta Net Sharpe (ann.): **1.031**
- Max DD (net): **-0.1188**

## Diebold–Mariano (daily next-day universe sign vs forecast log-loss)
- DM stat: **1.2751**
- p-value (two-sided): **2.0229e-01**
- Meta DM stat: **6.9337**
- Meta p-value (two-sided): **4.1003e-12**

## SPA-lite (block bootstrap on daily excess vs buy&hold)
- Observed mean excess: **-0.009618**
- One-sided p-value (H1: mean > 0): **0.5800**

## Interpretation (auto-generated checklist)
- **Horizons:** ranking metrics above use the same 5-day `fwd_5d` as the label; if IC/Rank IC and quantile spread still disagree, that is more likely **noise / weak signal / calibration** than a 1d-vs-5d definition bug.
- If **Rank IC** and **IC** are near zero and quantile spreads are weak, treat ranking signal as **not demonstrated** on this panel; focus on pipeline sanity, not live trading.
- Use **precision@k**, **quantile spread**, and **Sharpe/hit-rate** together; no single ranking metric is sufficient on noisy financial panels.
- Use **DM p-values** only in the sense documented above (daily sign vs probability); they do not validate the 5d label and do not guarantee economic value after costs.
- **SPA-lite** is a coarse block-bootstrap on mean excess; it is **not** full Hansen (2005) SPA across many models — see literature notes.
- Compare **net** backtest curves to gross when costs matter; meta-gated curve is exploratory (OOF primary + meta on train/val).

## Produced artifacts
- `RESEARCH_SUMMARY.md` (this file), `label_distribution.csv`
- `cv_fold_metrics.csv`, `cv_summary.csv`
- `model_metrics.csv`, `metric_sanity.csv`, `test_predictions.csv`, `feature_importance_top20.csv`
- `backtest_curves.csv`, `backtest_curves_meta.csv`, `backtest_stats.csv`, `spa_lite_holdout.csv`
- PNGs `01`–`08` (see folder)
