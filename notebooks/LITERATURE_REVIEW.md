# EquiSense Literature Notes (ML + Finance + NLP + Tuning)

Below are core references used to design the next notebook experiments.

## 1) XGBoost: A Scalable Tree Boosting System (Chen, Guestrin, KDD 2016)
- Link: https://arxiv.org/abs/1603.02754
- Key idea: regularized gradient boosting with strong handling of sparse features and efficient histogram/tree optimization.
- Why for us: robust baseline for tabular financial features (technical/fundamental/sentiment).
- Practical implication: tune `max_depth`, `learning_rate`, `n_estimators`, `subsample`, `colsample_bytree`, and regularization.

## 2) LightGBM: A Highly Efficient Gradient Boosting Decision Tree (Ke et al., NeurIPS 2017)
- Link: https://proceedings.neurips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html
- Key idea: GOSS + EFB for faster and memory-efficient boosting.
- Why for us: high-dimensional engineered features and quick iterative experiments.
- Practical implication: compare to XGBoost with equal CV protocol; include `num_leaves`, `feature_fraction`, `bagging_fraction`.

## 3) FinBERT: Financial Sentiment Analysis with Pre-trained Language Models (Araci, 2019)
- Link: https://arxiv.org/abs/1908.10063
- Key idea: domain-adapted BERT significantly improves financial sentiment tasks over general NLP models.
- Why for us: validates sentiment pipeline as an informative feature source.
- Practical implication: run sentiment in batch ETL and evaluate contribution via ablation (with/without sentiment).

## 4) Optuna: A Next-generation Hyperparameter Optimization Framework (Akiba et al., KDD 2019)
- Link: https://dl.acm.org/doi/10.1145/3292500.3330701
- Key idea: define-by-run search spaces + pruning for efficient optimization.
- Why for us: fast, reproducible HPO for boosting models and logistic baselines.
- Practical implication: optimize on time-series CV objective; track best trials and feature impact.

## 5) Stock Market Prediction Using Machine Learning Techniques: A Decade Survey (Srivastava et al., 2021)
- Link: https://www.mdpi.com/2079-9292/10/21/2717
- Key idea: no universal best model; feature engineering and robust validation dominate gains.
- Why for us: supports model-comparison setup A/B/C/D and strict separation of train/validation windows.
- Practical implication: emphasize time-aware validation and transparent baseline comparisons.

## 6) Machine learning techniques and data for stock market forecasting: A literature review (Bustos, Pomares-Quimbaya, 2022)
- Link: https://www.sciencedirect.com/science/article/pii/S0957417422001452
- Key idea: mixed data modalities (technical + textual + fundamentals) can improve predictive robustness if leakage is controlled.
- Why for us: aligns with our combined feature design.
- Practical implication: include leakage checks and target-shift diagnostics in EDA.

## 7) Stock Price Prediction Using Principal Components (PLOS ONE, 2020)
- Link: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0230124
- Key idea: PCA can reduce noise and multicollinearity before predictive modeling.
- Why for us: useful for correlated technical indicator blocks.
- Practical implication: evaluate PCA as optional preprocessing for linear/logistic models, compare to raw features.

## 8) Robust Rolling PCA / Time-varying factor approaches (SSRN and recent follow-ups)
- Example link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4400158
- Key idea: latent factors in financial data are non-stationary; rolling decomposition is often better than one-shot PCA.
- Why for us: helps interpret regime changes and factor drift.
- Practical implication: include rolling PCA visualization in EDA notebook.

## 9) López de Prado — *Advances in Financial Machine Learning* (Wiley, 2018)
- Key idea: financial labels overlap in time; standard k-fold leaks. Use **purged / combinatorial CV**, **sample weights by uniqueness**, **triple-barrier labels**, **meta-labeling** (secondary model on primary signals).
- Why for us: justifies CPCV, purged splits, embargo, OOF primary scores for meta — implemented in `backend/app/ml/` and `run_research_pack.py`.
- Practical implication: report CPCV and horizon-purged metrics alongside naive AUC; treat ~0.5 AUC as “no edge” unless economics + stats agree.

## 10) Diebold & Mariano — *Comparing predictive accuracy* (Journal of Business & Economic Statistics, 1995)
- Link: https://www.federalreserve.gov/pubs/feds/1994/199441/199441pap.pdf (working paper; widely cited)
- Key idea: HAC variance for mean loss differential between two forecasters.
- Why for us: `app/ml/finance_stats.diebold_mariano` + daily log-loss block in research pack.
- Practical implication: use as **diagnostic**, not sole proof of profitability.

## 11) Hansen — *A test for superior predictive ability* (Journal of Business & Economic Statistics, 2005)
- Key idea: SPA / reality-check style tests over many models vs a benchmark.
- Why for us: full SPA is heavier; we ship **SPA-lite** (block bootstrap on mean excess return vs B&H) in `spa_lite.py` — document as approximation, not full Hansen.

## 12) Imbalanced classification (general practice)
- Key idea: daily up/down labels are often near 50/50 but can drift; use **`class_weight='balanced'`** or **scale_pos_weight** for boosting.
- Why for us: aligned with `app/ml/training_pipeline.py` (production) and now with research-pack RF/logreg + OOF/meta RF.

---

## Planned implementation mapping

1. EDA notebook:
- distributions, missingness, correlation heatmaps, leakage checks, rolling stats.

2. Feature engineering notebook:
- technical/fundamental/sentiment joins, PCA and rolling PCA diagnostics.

3. Modeling notebook:
- logistic/xgboost/lightgbm with time-series split and Optuna tuning.
- ablations:
  - tech only
  - tech + fundamental
  - tech + sentiment
  - all features
