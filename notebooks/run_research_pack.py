"""
Rigorous research pack: walk-forward purged CV, ablations, costs, Diebold–Mariano.

Run from repo root:
  cd backend && uv run python ../notebooks/run_research_pack.py

Outputs under `notebooks/results/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PROCESSED = BACKEND / "data" / "processed"
OUT_DIR = ROOT / "notebooks" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.features.constants import (  # noqa: E402
    FUNDAMENTAL_FEATURES,
    LAG_FEATURES,
    SENTIMENT_FEATURES,
    TECHNICAL_FEATURES,
)
from app.features.feature_store import FeatureStore  # noqa: E402
from app.ml.cv import (  # noqa: E402
    combinatorial_purged_cv_splits,
    mask_for_dates,
    purged_kfold_splits,
    purged_kfold_with_horizon,
    walk_forward_expanding_splits,
)
from app.ml.evaluation import (  # noqa: E402
    financial_selection_metrics,
    information_coefficient_metrics,
    precision_recall_at_k,
    reliability_curve_and_ece,
)
from app.ml.finance_stats import (  # noqa: E402
    annualized_sharpe,
    diebold_mariano,
    max_drawdown,
    net_returns_with_transaction_costs,
)
from app.ml.meta_labeling import apply_meta_gating, build_meta_labels, fit_meta_model  # noqa: E402
from app.ml.oof import oof_primary_proba  # noqa: E402
from app.ml.spa_lite import block_bootstrap_mean_pvalue  # noqa: E402

sns.set_theme(style="whitegrid", context="talk")
np.random.seed(42)


def _load_combined_panel() -> pd.DataFrame:
    store = FeatureStore(data_root=BACKEND / "data")
    rows: list[pd.DataFrame] = []
    for ticker_dir in sorted(PROCESSED.glob("*")):
        if not ticker_dir.is_dir():
            continue
        t = ticker_dir.name.upper()
        try:
            combined = store.build_combined(t)
        except Exception:
            continue
        combined["date"] = pd.to_datetime(combined["date"])
        combined = combined.sort_values("date").reset_index(drop=True)
        combined["ticker"] = t
        combined["ret_1d"] = pd.to_numeric(combined["returns"], errors="coerce")
        # 5-day cumulative forward return (sum of next 5 daily returns)
        fwd_5d = combined["ret_1d"].rolling(5).sum().shift(-5)
        combined["target_up_5d"] = (fwd_5d > 0.01).astype(int)
        rows.append(combined.iloc[:-5].copy())

    if not rows:
        raise RuntimeError("No combined processed data for any ticker")

    return pd.concat(rows, ignore_index=True)


def _feature_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    cols = set(df.columns)
    tech = [c for c in TECHNICAL_FEATURES + LAG_FEATURES if c in cols]
    fund = [c for c in FUNDAMENTAL_FEATURES if c in cols]
    sent = [c for c in SENTIMENT_FEATURES if c in cols]
    return {
        "tech_only": tech,
        "tech_fund": tech + fund,
        "full": tech + fund + sent,
    }


def _label_dist_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_no data_"
    hdr = "| split | n | n_positive | n_negative | frac_positive |\n| --- | --- | --- | --- | --- |"
    rows = []
    for _, row in df.iterrows():
        rows.append(
            f"| {row['split']} | {row['n']} | {row['n_positive']} | {row['n_negative']} | "
            f"{float(row['frac_positive']):.4f} |"
        )
    return hdr + "\n" + "\n".join(rows)


def _label_split_stats(y: pd.Series, split: str) -> dict[str, object]:
    v = np.asarray(y).astype(int)
    n = len(v)
    n_pos = int((v == 1).sum())
    n_neg = int((v == 0).sum())
    return {
        "split": split,
        "n": n,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "frac_positive": float(n_pos / n) if n else float("nan"),
    }


def _metrics(
    y_true: pd.Series, proba: np.ndarray, eval_frame: pd.DataFrame | None = None
) -> dict[str, float]:
    pred = (proba >= 0.5).astype(int)
    out: dict[str, float] = {
        "accuracy": float(accuracy_score(y_true, pred)),
        "f1": float(f1_score(y_true, pred)),
        "roc_auc": float(roc_auc_score(y_true, proba)),
    }
    try:
        out["brier"] = float(brier_score_loss(y_true, proba))
    except ValueError:
        out["brier"] = float("nan")
    try:
        out["pr_auc"] = float(average_precision_score(y_true, proba))
    except ValueError:
        out["pr_auc"] = float("nan")
    rank = precision_recall_at_k(y_true, proba, k=max(1, int(len(y_true) * 0.25)))
    out["precision_at_k"] = float(rank["precision_at_k"])
    out["recall_at_k"] = float(rank["recall_at_k"])
    rel_df, ece = reliability_curve_and_ece(y_true, proba, n_bins=10)
    out["ece"] = float(ece)
    if eval_frame is not None and not eval_frame.empty:
        fm = financial_selection_metrics(eval_frame, score_col="score", return_col="forward_return")
        icm = information_coefficient_metrics(eval_frame, score_col="score", return_col="forward_return")
        out.update({k: float(v) for k, v in fm.items()})
        out.update({k: float(v) for k, v in icm.items()})
    out["_reliability_rows"] = rel_df.to_dict(orient="records")
    return out


def _fit_rf(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_val: pd.DataFrame | None,
    y_val: pd.Series | None,
    trials: int,
) -> tuple[RandomForestClassifier, SimpleImputer]:
    """Fit RandomForest with optional Optuna on validation subset."""
    imputer = SimpleImputer(strategy="median")
    x_tr = imputer.fit_transform(x_train)
    x_va = imputer.transform(x_val) if x_val is not None else None

    if x_va is None or trials <= 0:
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(x_tr, y_train)
        return rf, imputer

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 80, 320),
            "max_depth": trial.suggest_int("max_depth", 4, 14),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            "max_features": trial.suggest_float("max_features", 0.3, 1.0),
            "bootstrap": trial.suggest_categorical("bootstrap", [True, False]),
            "random_state": 42,
            "n_jobs": -1,
        }
        model = RandomForestClassifier(**params, class_weight="balanced")
        model.fit(x_tr, y_train)
        proba = model.predict_proba(x_va)[:, 1]
        return float(roc_auc_score(y_val, proba))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    rf = RandomForestClassifier(
        **study.best_params,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(x_tr, y_train)
    return rf, imputer


def _cv_metrics(
    df: pd.DataFrame,
    features: list[str],
    *,
    splits: list[tuple[np.ndarray, np.ndarray]],
    name: str,
) -> list[dict[str, object]]:
    d = df.dropna(subset=["target_up_5d"]).copy()
    dates = d["date"].values
    out: list[dict[str, object]] = []
    for fold, (train_d, test_d) in enumerate(splits):
        m_tr = mask_for_dates(dates, train_d)
        m_te = mask_for_dates(dates, test_d)
        if m_tr.sum() < 50 or m_te.sum() < 20:
            continue
        x_tr, y_tr = d.loc[m_tr, features], d.loc[m_tr, "target_up_5d"].astype(int)
        x_te, y_te = d.loc[m_te, features], d.loc[m_te, "target_up_5d"].astype(int)
        rf, imp = _fit_rf(x_tr, y_tr, None, None, trials=0)
        x_te_t = imp.transform(x_te)
        proba = rf.predict_proba(x_te_t)[:, 1]
        out.append(
            {
                "split_name": name,
                "fold": fold,
                "roc_auc": float(roc_auc_score(y_te, proba)),
                "f1": float(f1_score(y_te, (proba >= 0.5).astype(int))),
            }
        )
    return out


def _pick_threshold(
    proba: np.ndarray,
    ret: np.ndarray,
    *,
    grid: np.ndarray | None = None,
) -> float:
    grid = grid if grid is not None else np.linspace(0.45, 0.60, 31)
    best_t, best = 0.5, -np.inf
    for t in grid:
        sig = (proba >= t).astype(float)
        score = float(np.mean(sig * ret))
        if score > best:
            best, best_t = score, float(t)
    return best_t


def _backtest_daily(
    df: pd.DataFrame,
    *,
    proba_col: str,
    threshold: float,
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Equal-weight cross-sectional daily portfolio."""
    bt = df.copy()
    bt["signal"] = (bt[proba_col] >= threshold).astype(float)
    bt["gross_ret"] = bt["signal"] * bt["ret_1d"]
    daily = (
        bt.groupby("date", as_index=False)
        .agg({"ret_1d": "mean", "gross_ret": "mean", "signal": "mean"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["pos_change"] = daily["signal"].diff().abs().fillna(daily["signal"].iloc[0])
    cost = cost_bps / 10000.0
    daily["net_ret"] = net_returns_with_transaction_costs(
        daily["gross_ret"].values,
        daily["signal"].values,
        cost_per_turn=cost,
    )
    daily["buy_hold_equally_weighted"] = (1.0 + daily["ret_1d"].fillna(0.0)).cumprod()
    daily["strategy_curve_gross"] = (1.0 + daily["gross_ret"].fillna(0.0)).cumprod()
    daily["strategy_curve_net"] = (1.0 + daily["net_ret"].fillna(0.0)).cumprod()
    daily["strategy_dd"] = daily["strategy_curve_net"] / daily["strategy_curve_net"].cummax() - 1.0
    bh = daily["ret_1d"].values
    sn = daily["net_ret"].values
    stats = {
        "sharpe_bh": annualized_sharpe(bh),
        "sharpe_strategy_net": annualized_sharpe(sn),
        "max_dd_net": max_drawdown(daily["strategy_curve_net"].values),
    }
    return daily, stats


def _backtest_from_signal(
    df: pd.DataFrame,
    *,
    signal_col: str,
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    bt = df.copy()
    bt["signal"] = pd.to_numeric(bt[signal_col], errors="coerce").fillna(0.0)
    bt["gross_ret"] = bt["signal"] * bt["ret_1d"]
    daily = (
        bt.groupby("date", as_index=False)
        .agg({"ret_1d": "mean", "gross_ret": "mean", "signal": "mean"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    cost = cost_bps / 10000.0
    daily["net_ret"] = net_returns_with_transaction_costs(
        daily["gross_ret"].values,
        daily["signal"].values,
        cost_per_turn=cost,
    )
    daily["buy_hold_equally_weighted"] = (1.0 + daily["ret_1d"].fillna(0.0)).cumprod()
    daily["strategy_curve_gross"] = (1.0 + daily["gross_ret"].fillna(0.0)).cumprod()
    daily["strategy_curve_net"] = (1.0 + daily["net_ret"].fillna(0.0)).cumprod()
    daily["strategy_dd"] = daily["strategy_curve_net"] / daily["strategy_curve_net"].cummax() - 1.0
    stats = {
        "sharpe_bh": annualized_sharpe(daily["ret_1d"].values),
        "sharpe_strategy_net": annualized_sharpe(daily["net_ret"].values),
        "max_dd_net": max_drawdown(daily["strategy_curve_net"].values),
    }
    return daily, stats


def _backtest_top_k(
    df: pd.DataFrame,
    *,
    score_col: str,
    top_k: int = 10,
) -> tuple[pd.DataFrame, dict[str, float]]:
    bt = df[["date", "ticker", "ret_1d", score_col]].copy()
    bt = bt.rename(columns={score_col: "score"})
    bt = bt.dropna(subset=["date", "ticker", "ret_1d", "score"])
    picks = []
    for dt, g in bt.groupby("date"):
        gs = g.sort_values("score", ascending=False).copy()
        k = max(1, min(top_k, len(gs)))
        gs["selected"] = 0.0
        gs.iloc[:k, gs.columns.get_loc("selected")] = 1.0
        picks.append(gs)
    ranked = pd.concat(picks, ignore_index=True) if picks else bt.assign(selected=0.0)
    daily = (
        ranked.groupby("date", as_index=False)
        .agg({"ret_1d": "mean", "selected": "mean"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    sel_ret = (
        ranked[ranked["selected"] > 0.0]
        .groupby("date", as_index=False)["ret_1d"]
        .mean()
        .rename(columns={"ret_1d": "topk_ret"})
    )
    daily = daily.merge(sel_ret, on="date", how="left")
    daily["topk_ret"] = daily["topk_ret"].fillna(0.0)
    daily["curve_topk"] = (1.0 + daily["topk_ret"]).cumprod()
    daily["curve_universe"] = (1.0 + daily["ret_1d"]).cumprod()
    daily["turnover"] = daily["selected"].diff().abs().fillna(daily["selected"].iloc[0])
    stats = {
        "topk_sharpe": annualized_sharpe(daily["topk_ret"].values),
        "universe_sharpe": annualized_sharpe(daily["ret_1d"].values),
        "topk_turnover": float(daily["turnover"].mean()),
        "topk_cum_return": float(daily["curve_topk"].iloc[-1] - 1.0),
        "universe_cum_return": float(daily["curve_universe"].iloc[-1] - 1.0),
    }
    return daily, stats


def _diebold_on_test(
    df_test: pd.DataFrame,
    *,
    proba_col: str,
    threshold: float,
) -> dict[str, float]:
    """DM on daily direction log-loss (strategy forecast vs constant 0.5)."""
    bt = df_test.copy()
    p_raw = pd.to_numeric(bt[proba_col], errors="coerce").clip(0.0, 1.0)
    # If column looks binary, convert with threshold; otherwise preserve probabilities.
    uniq = set(np.unique(p_raw.dropna().round(6)))
    if uniq.issubset({0.0, 1.0}):
        bt["forecast_proba"] = (p_raw >= threshold).astype(float)
    else:
        bt["forecast_proba"] = p_raw
    daily = bt.groupby("date", as_index=False).agg({"ret_1d": "mean", "forecast_proba": "mean"})
    y = (daily["ret_1d"].fillna(0.0) > 0).astype(float).values
    p = np.clip(daily["forecast_proba"].values, 0.01, 0.99)
    loss_s = -np.log(p) * y - np.log(1.0 - p) * (1.0 - y)
    loss_b = -np.log(0.5) * y - np.log(0.5) * (1.0 - y)
    return diebold_mariano(loss_s, loss_b, h=5)


def run_pipeline(
    *,
    optuna_trials: int,
    cost_bps: float,
    cpcv_groups: int,
    cpcv_max_splits: int,
    spa_bootstrap: int,
) -> None:
    panel = _load_combined_panel()
    groups = _feature_groups(panel)
    udates = np.sort(panel["date"].unique())

    wf = walk_forward_expanding_splits(udates, n_splits=4)
    pk = purged_kfold_splits(udates, n_splits=5, embargo_days=5)
    pkh = purged_kfold_with_horizon(
        udates,
        n_splits=5,
        label_horizon_days=1,
        embargo_days=5,
    )
    cpcv = combinatorial_purged_cv_splits(
        udates,
        n_groups=cpcv_groups,
        test_n_groups=2,
        embargo_days=5,
        label_horizon_days=1,
        max_splits=cpcv_max_splits,
    )

    cv_rows: list[dict[str, object]] = []
    for ab_name, feats in groups.items():
        if len(feats) < 2:
            continue
        df_ab = panel.copy()
        for row in _cv_metrics(df_ab, feats, splits=wf, name="walk_forward"):
            row["ablation"] = ab_name
            cv_rows.append(row)
        for row in _cv_metrics(df_ab, feats, splits=pk, name="purged_kfold"):
            row["ablation"] = ab_name
            cv_rows.append(row)
        for row in _cv_metrics(df_ab, feats, splits=pkh, name="purged_kfold_horizon"):
            row["ablation"] = ab_name
            cv_rows.append(row)
    if cpcv and len(groups["full"]) >= 2:
        df_full = panel.copy()
        for row in _cv_metrics(df_full, groups["full"], splits=cpcv, name="cpcv"):
            row["ablation"] = "full"
            cv_rows.append(row)

    cv_df = pd.DataFrame(cv_rows)
    cv_df.to_csv(OUT_DIR / "cv_fold_metrics.csv", index=False)

    # Holdout: last 15% dates = test; middle 70% train; 15% before test = val for threshold
    n_d = len(udates)
    i_test = int(0.85 * n_d)
    test_dates = udates[i_test:]
    val_end = i_test
    val_start = int(0.70 * n_d)
    val_dates = udates[val_start:val_end]
    train_dates = udates[:val_start]

    full_feats = groups["full"]
    d = panel.dropna(subset=["target_up_5d"]).copy()
    dt = d["date"].values
    m_tr = mask_for_dates(dt, train_dates)
    m_va = mask_for_dates(dt, val_dates)
    m_te = mask_for_dates(dt, test_dates)

    x_tr, y_tr = d.loc[m_tr, full_feats], d.loc[m_tr, "target_up_5d"].astype(int)
    x_va, y_va = d.loc[m_va, full_feats], d.loc[m_va, "target_up_5d"].astype(int)
    x_te, y_te = d.loc[m_te, full_feats], d.loc[m_te, "target_up_5d"].astype(int)

    label_dist = pd.DataFrame(
        [
            _label_split_stats(y_tr, "train"),
            _label_split_stats(y_va, "validation"),
            _label_split_stats(y_te, "test"),
        ]
    )
    label_dist.to_csv(OUT_DIR / "label_distribution.csv", index=False)

    # Baseline + PCA + RF
    baseline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=1200,
                    random_state=42,
                    class_weight="balanced",
                ),
            ),
        ]
    )
    baseline.fit(x_tr, y_tr)
    proba_base_te = baseline.predict_proba(x_te)[:, 1]

    pca = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("pca", PCA(n_components=0.95, random_state=42)),
            (
                "clf",
                LogisticRegression(
                    max_iter=1200,
                    random_state=42,
                    class_weight="balanced",
                ),
            ),
        ]
    )
    pca.fit(x_tr, y_tr)
    proba_pca_te = pca.predict_proba(x_te)[:, 1]

    rf, imputer = _fit_rf(x_tr, y_tr, x_va, y_va, trials=optuna_trials)
    x_te_t = imputer.transform(x_te)
    proba_rf_te = rf.predict_proba(x_te_t)[:, 1]

    # XGBoost with Optuna
    pos = int(y_tr.sum()); neg = int((y_tr == 0).sum())
    spw = neg / pos if pos > 0 else 1.0
    x_tr_imp = imputer.transform(x_tr)
    x_va_imp = imputer.transform(x_va)

    def _xgb_objective(trial: optuna.Trial) -> float:
        clf = XGBClassifier(
            n_estimators=trial.suggest_int("n_estimators", 100, 500),
            max_depth=trial.suggest_int("max_depth", 3, 7),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
            min_child_weight=trial.suggest_int("min_child_weight", 1, 10),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            scale_pos_weight=spw,
            eval_metric="logloss",
            random_state=42,
        )
        clf.fit(x_tr_imp, y_tr)
        p = clf.predict_proba(x_va_imp)[:, 1]
        return float(roc_auc_score(y_va, p))

    xgb_study = optuna.create_study(direction="maximize")
    xgb_study.optimize(_xgb_objective, n_trials=optuna_trials or 30, show_progress_bar=False)
    best_xgb = XGBClassifier(**xgb_study.best_params, scale_pos_weight=spw,
                              eval_metric="logloss", random_state=42)
    best_xgb.fit(x_tr_imp, y_tr)
    proba_xgb_te = best_xgb.predict_proba(x_te_t)[:, 1]

    # LightGBM with Optuna
    def _lgbm_objective(trial: optuna.Trial) -> float:
        clf = LGBMClassifier(
            n_estimators=trial.suggest_int("n_estimators", 100, 500),
            num_leaves=trial.suggest_int("num_leaves", 20, 150),
            max_depth=trial.suggest_int("max_depth", 3, 8),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            feature_fraction=trial.suggest_float("feature_fraction", 0.5, 1.0),
            bagging_fraction=trial.suggest_float("bagging_fraction", 0.5, 1.0),
            bagging_freq=trial.suggest_int("bagging_freq", 1, 7),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            class_weight="balanced",
            random_state=42,
            verbosity=-1,
        )
        clf.fit(x_tr_imp, y_tr)
        p = clf.predict_proba(x_va_imp)[:, 1]
        return float(roc_auc_score(y_va, p))

    lgbm_study = optuna.create_study(direction="maximize")
    lgbm_study.optimize(_lgbm_objective, n_trials=optuna_trials or 30, show_progress_bar=False)
    best_lgbm = LGBMClassifier(**lgbm_study.best_params, class_weight="balanced",
                                random_state=42, verbosity=-1)
    best_lgbm.fit(x_tr_imp, y_tr)
    proba_lgbm_te = best_lgbm.predict_proba(x_te_t)[:, 1]

    eval_base = d.loc[m_te, ["date", "ticker", "ret_1d"]].copy()
    eval_base = eval_base.rename(columns={"ret_1d": "forward_return"})
    metrics_rows = []
    reliability_rows = []
    for model_name, model_proba in [
        ("logreg_baseline", proba_base_te),
        ("logreg_pca", proba_pca_te),
        ("random_forest_optuna", proba_rf_te),
        ("xgboost_optuna", proba_xgb_te),
        ("lightgbm_optuna", proba_lgbm_te),
    ]:
        ef = eval_base.copy()
        ef["score"] = model_proba
        m = _metrics(y_te, model_proba, ef)
        rel = m.pop("_reliability_rows", [])
        for row in rel:
            reliability_rows.append({"model": model_name, **row})
        metrics_rows.append({"model": model_name, **m})
    metrics_df = pd.DataFrame(metrics_rows).sort_values("roc_auc", ascending=False)
    metrics_df.to_csv(OUT_DIR / "model_metrics.csv", index=False)
    pd.DataFrame(reliability_rows).to_csv(OUT_DIR / "reliability_curve.csv", index=False)

    test_out = d.loc[m_te, ["date", "ticker", "ret_1d"]].copy()
    test_out["proba_baseline"] = proba_base_te
    test_out["proba_pca"] = proba_pca_te
    test_out["proba_rf"] = proba_rf_te
    test_out["proba_xgb"] = proba_xgb_te
    test_out["proba_lgbm"] = proba_lgbm_te

    # Use best model (by val AUC) for backtesting
    _val_aucs = {
        "proba_rf": float(roc_auc_score(y_va, rf.predict_proba(x_va_imp)[:, 1])),
        "proba_xgb": float(xgb_study.best_value),
        "proba_lgbm": float(lgbm_study.best_value),
    }
    _best_proba_col = max(_val_aucs, key=_val_aucs.__getitem__)

    fi = pd.Series(rf.feature_importances_, index=full_feats).sort_values(ascending=False)
    fi.head(20).rename("importance").to_csv(OUT_DIR / "feature_importance_top20.csv")

    # Threshold on validation (best model by val AUC)
    _best_va_proba = {
        "proba_rf": rf.predict_proba(x_va_imp)[:, 1],
        "proba_xgb": best_xgb.predict_proba(x_va_imp)[:, 1],
        "proba_lgbm": best_lgbm.predict_proba(x_va_imp)[:, 1],
    }[_best_proba_col]
    thr = _pick_threshold(_best_va_proba, d.loc[m_va, "ret_1d"].values)

    _backtest_daily(
        test_out,
        proba_col=_best_proba_col,
        threshold=thr,
        cost_bps=0.0,
    )
    daily_net, stats_net = _backtest_daily(
        test_out,
        proba_col=_best_proba_col,
        threshold=thr,
        cost_bps=cost_bps,
    )
    daily_net.to_csv(OUT_DIR / "backtest_curves.csv", index=False)

    spread = daily_net["net_ret"].values - daily_net["ret_1d"].values
    spa = block_bootstrap_mean_pvalue(spread, n_bootstrap=spa_bootstrap, block_len=5)
    pd.DataFrame([spa]).to_csv(OUT_DIR / "spa_lite_holdout.csv", index=False)

    # Meta-labeling with OOF primary probabilities on train+val (reduces leakage).
    # Same scheme as purged_kfold_with_horizon (label overlap + embargo), not walk-forward.
    m_tv = m_tr | m_va
    d_tv = d.loc[m_tv].copy().reset_index(drop=True)
    u_tv = np.sort(d_tv["date"].unique())
    n_tv = len(u_tv)
    oof_n_splits = 5 if n_tv > 200 else 4 if n_tv > 120 else 3 if n_tv > 80 else 2
    oof_splits = purged_kfold_with_horizon(
        u_tv,
        n_splits=oof_n_splits,
        label_horizon_days=1,
        embargo_days=5,
    )
    if not oof_splits:
        oof_splits = walk_forward_expanding_splits(u_tv, n_splits=max(1, min(2, n_tv // 40)))
    d_tv["proba_primary_oof"] = oof_primary_proba(
        d_tv,
        full_feats,
        "target_up_5d",
        "date",
        oof_splits,
    )
    meta_train = d_tv.dropna(subset=["proba_primary_oof"]).copy()
    meta_train["proba_primary_for_meta"] = meta_train["proba_primary_oof"]
    if len(meta_train) < 80:
        val_df = d.loc[m_va].copy().reset_index(drop=True)
        val_df["proba_primary_for_meta"] = _best_va_proba
        meta_train = val_df
        y_meta_val = build_meta_labels(
            meta_train,
            ret_col="ret_1d",
            primary_proba_col="proba_primary_for_meta",
            threshold=thr,
        )
        meta_x_tv = meta_train[full_feats + ["proba_primary_for_meta"]]
        meta_model, meta_imp = fit_meta_model(meta_x_tv, y_meta_val)
    else:
        y_meta_val = build_meta_labels(
            meta_train,
            ret_col="ret_1d",
            primary_proba_col="proba_primary_for_meta",
            threshold=thr,
        )
        meta_x_tv = meta_train[full_feats + ["proba_primary_for_meta"]]
        meta_model, meta_imp = fit_meta_model(meta_x_tv, y_meta_val)

    meta_x_test = test_out.merge(
        d.loc[m_te, ["date", "ticker"] + full_feats],
        on=["date", "ticker"],
        how="left",
    )
    meta_x_test["proba_primary_for_meta"] = test_out["proba_rf"].values
    meta_proba_te = meta_model.predict_proba(
        meta_imp.transform(meta_x_test[full_feats + ["proba_primary_for_meta"]])
    )[:, 1]
    test_out["proba_meta"] = meta_proba_te
    test_out["signal_meta"] = apply_meta_gating(
        test_out["proba_rf"].values,
        test_out["proba_meta"].values,
        primary_threshold=thr,
        meta_threshold=0.55,
    )
    test_out.to_csv(OUT_DIR / "test_predictions.csv", index=False)

    daily_meta, stats_meta = _backtest_from_signal(
        test_out,
        signal_col="signal_meta",
        cost_bps=cost_bps,
    )
    daily_meta.to_csv(OUT_DIR / "backtest_curves_meta.csv", index=False)
    daily_topk, stats_topk = _backtest_top_k(
        test_out,
        score_col=_best_proba_col,
        top_k=10,
    )
    daily_topk.to_csv(OUT_DIR / "backtest_curves_topk.csv", index=False)

    dm = _diebold_on_test(test_out, proba_col="proba_rf", threshold=thr)
    test_out["proba_meta_gated"] = test_out["proba_rf"] * (test_out["proba_meta"] >= 0.55).astype(float)
    dm_meta = _diebold_on_test(
        test_out,
        proba_col="proba_meta_gated",
        threshold=0.5,
    )
    stats_row = {
        **stats_net,
        "meta_sharpe_strategy_net": stats_meta["sharpe_strategy_net"],
        "meta_max_dd_net": stats_meta["max_dd_net"],
        "dm_stat": dm["dm_stat"],
        "dm_p_value_two_sided": dm["p_value_two_sided"],
        "dm_mean_d": dm["mean_d"],
        "dm_var_mean_d": dm["var_mean_d"],
        "dm_meta_stat": dm_meta["dm_stat"],
        "dm_meta_p_value_two_sided": dm_meta["p_value_two_sided"],
        "spa_p_value_one_sided": spa["p_value_one_sided"],
        "spa_observed_mean": spa["observed_mean"],
        "threshold": thr,
    }
    pd.DataFrame([stats_row]).to_csv(OUT_DIR / "backtest_stats.csv", index=False)
    pd.DataFrame([stats_topk]).to_csv(OUT_DIR / "backtest_topk_stats.csv", index=False)

    # Aggregated model comparison dashboard.
    baseline_auc = float(metrics_df.loc[metrics_df["model"] == "logreg_baseline", "roc_auc"].iloc[0])
    dashboard = metrics_df[
        [
            "model",
            "roc_auc",
            "ic_mean",
            "rank_ic_mean",
            "long_short_spread",
            "top_quantile_return",
        ]
    ].copy()
    dashboard["mean_auc"] = dashboard["roc_auc"]
    dashboard["mean_ic"] = dashboard["ic_mean"]
    dashboard["average_return"] = dashboard["top_quantile_return"]
    dashboard["beats_baseline_auc"] = (dashboard["roc_auc"] > baseline_auc).astype(int)
    dashboard["beat_baseline_pct"] = dashboard["beats_baseline_auc"] * 100.0
    best_col_to_model = {
        "proba_rf": "random_forest_optuna",
        "proba_xgb": "xgboost_optuna",
        "proba_lgbm": "lightgbm_optuna",
    }
    dashboard["sharpe_ratio"] = np.where(
        dashboard["model"] == best_col_to_model.get(_best_proba_col, ""),
        stats_net.get("sharpe_strategy_net", np.nan),
        np.nan,
    )
    dashboard.to_csv(OUT_DIR / "model_comparison_dashboard.csv", index=False)

    pd.DataFrame(
        [
            {
                "name": "walk_forward_mean_auc",
                "value": cv_df[cv_df["split_name"] == "walk_forward"]["roc_auc"].mean(),
            },
            {
                "name": "walk_forward_std_auc",
                "value": cv_df[cv_df["split_name"] == "walk_forward"]["roc_auc"].std(ddof=1),
            },
            {
                "name": "purged_kfold_mean_auc",
                "value": cv_df[cv_df["split_name"] == "purged_kfold"]["roc_auc"].mean(),
            },
            {
                "name": "purged_kfold_std_auc",
                "value": cv_df[cv_df["split_name"] == "purged_kfold"]["roc_auc"].std(ddof=1),
            },
            {
                "name": "purged_kfold_horizon_mean_auc",
                "value": cv_df[cv_df["split_name"] == "purged_kfold_horizon"]["roc_auc"].mean(),
            },
            {
                "name": "purged_kfold_horizon_std_auc",
                "value": cv_df[cv_df["split_name"] == "purged_kfold_horizon"]["roc_auc"].std(ddof=1),
            },
            {
                "name": "cpcv_mean_auc",
                "value": cv_df[cv_df["split_name"] == "cpcv"]["roc_auc"].mean()
                if not cv_df.empty and (cv_df["split_name"] == "cpcv").any()
                else float("nan"),
            },
            {
                "name": "cpcv_std_auc",
                "value": cv_df[cv_df["split_name"] == "cpcv"]["roc_auc"].std(ddof=1)
                if not cv_df.empty and (cv_df["split_name"] == "cpcv").any()
                else float("nan"),
            },
        ]
    ).to_csv(OUT_DIR / "cv_summary.csv", index=False)

    trials_df = pd.DataFrame()  # placeholder if Optuna trials not stored
    _plots(
        panel,
        metrics_df,
        trials_df,
        fi,
        daily_net,
        daily_meta,
        cv_df,
        groups,
    )
    _report(
        metrics_df,
        daily_net,
        daily_meta,
        cv_df,
        groups,
        thr,
        cost_bps,
        dm,
        dm_meta,
        stats_net,
        stats_meta,
        spa,
        label_dist,
    )


def _plots(
    panel: pd.DataFrame,
    metrics_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    fi: pd.Series,
    backtest: pd.DataFrame,
    backtest_meta: pd.DataFrame,
    cv_df: pd.DataFrame,
    groups: dict[str, list[str]],
) -> None:
    plt.figure(figsize=(14, 7))
    sns.histplot(data=panel, x="ret_1d", bins=120, kde=True, color="#1f77b4")
    plt.title("Distribution of Daily Returns Across Tickers")
    plt.xlabel("Daily return")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "01_returns_distribution.png", dpi=160)
    plt.close()

    corr_cols = [c for c in ["ret_1d", "rsi", "macd", "macd_signal"] if c in panel.columns]
    if len(corr_cols) >= 2:
        plt.figure(figsize=(10, 8))
        sns.heatmap(panel[corr_cols].corr(), annot=True, cmap="coolwarm", fmt=".2f")
        plt.title("Correlation Heatmap (Core Features)")
        plt.tight_layout()
        plt.savefig(OUT_DIR / "02_correlation_heatmap.png", dpi=160)
        plt.close()

    plt.figure(figsize=(11, 6))
    sns.barplot(
        data=metrics_df.melt(id_vars="model", var_name="metric", value_name="value"),
        x="model",
        y="value",
        hue="metric",
    )
    plt.title("Holdout Model Comparison: Accuracy / F1 / ROC-AUC")
    plt.ylabel("Score")
    plt.xticks(rotation=12)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "03_model_metrics.png", dpi=160)
    plt.close()

    if not trials_df.empty:
        td = trials_df.dropna(subset=["value"]).sort_values("number")
        plt.figure(figsize=(12, 6))
        sns.lineplot(data=td, x="number", y="value", marker="o")
        plt.title("Optuna Trial Progress (Validation ROC-AUC)")
        plt.xlabel("Trial")
        plt.ylabel("ROC-AUC")
        plt.tight_layout()
        plt.savefig(OUT_DIR / "04_optuna_progress.png", dpi=160)
        plt.close()

    top_fi = fi.head(15).sort_values(ascending=True)
    plt.figure(figsize=(10, 8))
    sns.barplot(x=top_fi.values, y=top_fi.index, orient="h", hue=top_fi.index, palette="viridis", legend=False)
    plt.title("Top-15 RandomForest Feature Importance")
    plt.xlabel("Importance")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "05_feature_importance.png", dpi=160)
    plt.close()

    plt.figure(figsize=(12, 6))
    sns.lineplot(data=backtest, x="date", y="buy_hold_equally_weighted", label="buy_hold_equal")
    sns.lineplot(data=backtest, x="date", y="strategy_curve_gross", label="strategy_gross")
    sns.lineplot(data=backtest, x="date", y="strategy_curve_net", label="strategy_net")
    sns.lineplot(data=backtest_meta, x="date", y="strategy_curve_net", label="strategy_meta_net")
    plt.title("Backtest Equity Curves (holdout)")
    plt.ylabel("Equity (start=1.0)")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "06_backtest_curves.png", dpi=160)
    plt.close()

    if not cv_df.empty:
        plt.figure(figsize=(12, 6))
        sns.lineplot(data=cv_df, x="fold", y="roc_auc", hue="ablation", style="split_name", markers=True)
        plt.title("CV ROC-AUC by fold (ablations)")
        plt.tight_layout()
        plt.savefig(OUT_DIR / "07_cv_folds.png", dpi=160)
        plt.close()

        plt.figure(figsize=(10, 6))
        sns.barplot(data=cv_df, x="ablation", y="roc_auc", hue="split_name")
        plt.title("Mean CV quality by ablation")
        plt.xticks(rotation=15)
        plt.tight_layout()
        plt.savefig(OUT_DIR / "08_ablation_cv.png", dpi=160)
        plt.close()


def _report(
    metrics_df: pd.DataFrame,
    backtest: pd.DataFrame,
    backtest_meta: pd.DataFrame,
    cv_df: pd.DataFrame,
    groups: dict[str, list[str]],
    threshold: float,
    cost_bps: float,
    dm: dict[str, float],
    dm_meta: dict[str, float],
    stats_net: dict[str, float],
    stats_meta: dict[str, float],
    spa: dict[str, float],
    label_dist: pd.DataFrame,
) -> None:
    winner = metrics_df.iloc[0]
    final_bh = float(backtest["buy_hold_equally_weighted"].iloc[-1])
    final_net = float(backtest["strategy_curve_net"].iloc[-1])
    final_meta = float(backtest_meta["strategy_curve_net"].iloc[-1])
    uplift = (final_net / final_bh - 1.0) * 100.0 if final_bh > 0 else np.nan

    wf_mean = (
        cv_df[cv_df["split_name"] == "walk_forward"]["roc_auc"].mean()
        if not cv_df.empty
        else float("nan")
    )
    pk_mean = (
        cv_df[cv_df["split_name"] == "purged_kfold"]["roc_auc"].mean()
        if not cv_df.empty
        else float("nan")
    )
    pkh_mean = (
        cv_df[cv_df["split_name"] == "purged_kfold_horizon"]["roc_auc"].mean()
        if not cv_df.empty
        else float("nan")
    )
    cpcv_mean = (
        cv_df[cv_df["split_name"] == "cpcv"]["roc_auc"].mean()
        if not cv_df.empty and (cv_df["split_name"] == "cpcv").any()
        else float("nan")
    )

    label_md = _label_dist_markdown(label_dist)

    text = f"""# Research Pack Summary (rigorous)

Generated from `backend/data/processed` with **walk-forward expanding CV**, **purged k-fold + embargo**,
**holdout test**, **transaction costs**, **Diebold–Mariano** on daily losses.

See **`notebooks/LITERATURE_REVIEW.md`** for paper references (XGB/LightGBM/FinBERT/Optuna + validation/statistics).
See **`notebooks/RESEARCH_OUTPUTS.md`** for where every artifact is written.

## Class balance & modeling choices (this run)
- Logistic baselines: `class_weight=balanced`; RandomForest / meta / OOF RF: `class_weight=balanced` (aligned with production training helpers).
- Median imputation for all sklearn pipelines in this pack.

## Label distribution (next-day up), by time split
{label_md}

## Validation & leakage control
- Target: `target_up_5d` = (next-day return > 0); features at `t` do not use future prices beyond the
  engineered pipeline.
- Walk-forward expanding splits and purged k-fold reduce overlap between train and test in time.
- Threshold for strategy (`p >= {threshold:.2f}`) chosen on **validation** only, **not** on holdout.

## Holdout metrics (best row by ROC-AUC)
- **{winner["model"]}**: roc_auc={winner["roc_auc"]:.4f}, pr_auc={winner.get("pr_auc", float("nan")):.4f}, brier={winner.get("brier", float("nan")):.4f}, f1={winner["f1"]:.4f}

## Cross-validation (mean ROC-AUC across folds)
- Walk-forward: **{wf_mean:.4f}**
- Purged k-fold: **{pk_mean:.4f}**
- Purged k-fold + horizon: **{pkh_mean:.4f}**
- CPCV (combinatorial purged, full features): **{cpcv_mean:.4f}**

## Ablations (feature groups)
- `tech_only`: {len(groups["tech_only"])} features
- `tech_fund`: {len(groups["tech_fund"])} features
- `full`: {len(groups["full"])} features

## Backtest (holdout, equal-weight, costs {cost_bps} bps per side on turnover)
- Strategy equity (net): **{final_net:.3f}** vs buy-and-hold **{final_bh:.3f}**
- Meta-gated strategy equity (net): **{final_meta:.3f}**
- Relative uplift vs B&H: **{uplift:.2f}%**
- Net Sharpe (ann.): **{stats_net.get("sharpe_strategy_net", float("nan")):.3f}**
- Meta Net Sharpe (ann.): **{stats_meta.get("sharpe_strategy_net", float("nan")):.3f}**
- Max DD (net): **{stats_net.get("max_dd_net", float("nan")):.4f}**

## Diebold–Mariano (strategy vs benchmark log-loss)
- DM stat: **{dm.get("dm_stat", float("nan")):.4f}**
- p-value (two-sided): **{dm.get("p_value_two_sided", float("nan")):.4e}**
- Meta DM stat: **{dm_meta.get("dm_stat", float("nan")):.4f}**
- Meta p-value (two-sided): **{dm_meta.get("p_value_two_sided", float("nan")):.4e}**

## SPA-lite (block bootstrap on daily excess vs buy&hold)
- Observed mean excess: **{spa.get("observed_mean", float("nan")):.6f}**
- One-sided p-value (H1: mean > 0): **{spa.get("p_value_one_sided", float("nan")):.4f}**

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
"""
    (OUT_DIR / "RESEARCH_SUMMARY.md").write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--optuna-trials", type=int, default=20, help="Optuna trials for RF on train/val")
    p.add_argument("--cost-bps", type=float, default=2.0, help="Transaction cost per side in bps")
    p.add_argument("--cpcv-groups", type=int, default=8, help="Timeline groups for CPCV")
    p.add_argument("--cpcv-max-splits", type=int, default=20, help="Max CPCV combinations to evaluate")
    p.add_argument("--spa-bootstrap", type=int, default=2000, help="Bootstrap draws for SPA-lite")
    args = p.parse_args()
    run_pipeline(
        optuna_trials=args.optuna_trials,
        cost_bps=args.cost_bps,
        cpcv_groups=args.cpcv_groups,
        cpcv_max_splits=args.cpcv_max_splits,
        spa_bootstrap=args.spa_bootstrap,
    )
    print(f"Research pack generated in: {OUT_DIR}")


if __name__ == "__main__":
    main()
