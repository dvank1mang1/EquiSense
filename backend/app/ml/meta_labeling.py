"""Meta-labeling helpers (Lopez de Prado style gating)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer


def build_meta_labels(
    df: pd.DataFrame,
    *,
    primary_proba_col: str = "proba_primary",
    threshold: float = 0.5,
    target_col: str | None = None,
    ret_col: str = "ret_1d",
) -> pd.Series:
    """
    Binary meta-label: 1 iff primary call matches the realized outcome.

    - If ``target_col`` is set (e.g. ``target_up_5d``), compare ``y_hat`` to that column.
    - Else fallback: primary predicts next-day sign vs ``ret_col`` (legacy one-day horizon).
    """
    p = pd.to_numeric(df[primary_proba_col], errors="coerce")
    y_hat = (p >= threshold).astype(int)
    if target_col is not None:
        if target_col not in df.columns:
            raise KeyError(f"build_meta_labels: missing target column {target_col!r}")
        y_true = pd.to_numeric(df[target_col], errors="coerce").fillna(0).astype(int)
    else:
        y_true = (pd.to_numeric(df[ret_col], errors="coerce") > 0).astype(int)
    return (y_hat == y_true).astype(int)


def fit_meta_model(
    x_train: pd.DataFrame,
    y_meta_train: pd.Series,
) -> tuple[RandomForestClassifier, SimpleImputer]:
    imputer = SimpleImputer(strategy="median")
    x_tr = imputer.fit_transform(x_train)
    clf = RandomForestClassifier(
        n_estimators=250,
        max_depth=10,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(x_tr, y_meta_train.astype(int))
    return clf, imputer


def apply_meta_gating(
    primary_proba: np.ndarray,
    meta_proba: np.ndarray,
    *,
    primary_threshold: float,
    meta_threshold: float,
) -> np.ndarray:
    """
    Position is taken only when:
    - primary predicts up
    - meta confidence that primary is correct exceeds threshold
    """
    p1 = np.asarray(primary_proba, dtype=float).ravel()
    pm = np.asarray(meta_proba, dtype=float).ravel()
    if p1.shape != pm.shape:
        raise ValueError("primary_proba and meta_proba must have equal lengths")
    return ((p1 >= primary_threshold) & (pm >= meta_threshold)).astype(float)
