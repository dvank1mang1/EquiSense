"""Production training helpers: median imputation + class-imbalance handling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.models.base import BaseMLModel


def _scale_pos_weight(y: pd.Series) -> float:
    yv = np.asarray(y).astype(int)
    n_pos = int((yv == 1).sum())
    n_neg = int((yv == 0).sum())
    if n_pos < 1 or n_neg < 1:
        return 1.0
    return float(n_neg / n_pos)


def _apply_balance_to_leaf(est: object, y: pd.Series) -> None:
    w = _scale_pos_weight(y)
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from xgboost import XGBClassifier

        if isinstance(est, XGBClassifier):
            est.set_params(scale_pos_weight=w)
            return
        if isinstance(est, RandomForestClassifier):
            est.set_params(class_weight="balanced")
            return
        if isinstance(est, HistGradientBoostingClassifier):
            est.set_params(class_weight="balanced")
            return
    except (ImportError, OSError, ValueError):
        pass
    try:
        from lightgbm import LGBMClassifier

        if isinstance(est, LGBMClassifier):
            est.set_params(scale_pos_weight=w)
    except (ImportError, OSError, ValueError):
        pass


def _apply_balance_recursive(est: object, y: pd.Series) -> None:
    from sklearn.ensemble import VotingClassifier

    if isinstance(est, VotingClassifier):
        for _, sub in est.estimators:
            _apply_balance_recursive(sub, y)
        return
    _apply_balance_to_leaf(est, y)


def fit_production_pipeline(
    instance: BaseMLModel, x_train: pd.DataFrame, y_train: pd.Series
) -> None:
    """
    Wrap the estimator in Pipeline(imputer, model) with median imputation on train,
    and set imbalance-aware hyperparameters on tree/boosting estimators before fit.

    Baseline LR already uses an internal Pipeline(scaler, lr) with class_weight; we only
    prepend a median imputer.
    """
    feats = instance.feature_set
    x_fit = x_train[feats]
    inner = instance.model

    if isinstance(inner, Pipeline) and "lr" in inner.named_steps:
        imputer = SimpleImputer(strategy="median")
        full = Pipeline([("imputer", imputer), ("prep", inner)])
        full.fit(x_fit, y_train)
        instance.model = full
    else:
        _apply_balance_recursive(inner, y_train)
        imputer = SimpleImputer(strategy="median")
        full = Pipeline([("imputer", imputer), ("clf", inner)])
        full.fit(x_fit, y_train)
        instance.model = full

    instance.is_trained = True


def calibrate_production_model(
    instance: BaseMLModel,
    x_val: pd.DataFrame,
    y_val: pd.Series,
    *,
    min_samples: int = 50,
) -> str:
    """
    Isotonic calibration on validation (estimator must already be fitted on train).

    Returns a short status code for metrics: ``isotonic_applied`` or ``skipped_*``.
    """
    from sklearn.calibration import CalibratedClassifierCV

    feats = instance.feature_set
    xv = x_val[feats]
    yv = y_val.astype(int).values
    if len(xv) < min_samples:
        return f"skipped_val_lt_{min_samples}"
    if len(np.unique(yv)) < 2:
        return "skipped_single_class_in_val"
    try:
        cal = CalibratedClassifierCV(
            estimator=instance.model,
            cv="prefit",
            method="isotonic",
        )
        cal.fit(xv, yv)
        instance.model = cal
    except Exception:
        logger.exception("isotonic calibration fit failed")
        return "skipped_calibrator_fit_error"
    return "isotonic_applied"
