"""Out-of-fold primary model predictions for meta-labeling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer


def oof_primary_proba(
    df: pd.DataFrame,
    features: list[str],
    target_col: str,
    date_col: str,
    splits: list[tuple[np.ndarray, np.ndarray]],
    *,
    random_state: int = 42,
) -> pd.Series:
    """
    Fill OOF predicted probabilities for primary (direction) model.

    Each row must appear in exactly one test fold (caller should ensure splits partition
    the evaluation window). Rows not in any test fold get NaN.
    """
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for train_d, test_d in splits:
        m_tr = df[date_col].isin(pd.to_datetime(train_d).normalize())
        m_te = df[date_col].isin(pd.to_datetime(test_d).normalize())
        if m_tr.sum() < 30 or m_te.sum() < 10:
            continue
        x_tr = df.loc[m_tr, features]
        y_tr = df.loc[m_tr, target_col].astype(int)
        x_te = df.loc[m_te, features]
        imp = SimpleImputer(strategy="median")
        x_tr_i = imp.fit_transform(x_tr)
        x_te_i = imp.transform(x_te)
        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
        clf.fit(x_tr_i, y_tr)
        proba = clf.predict_proba(x_te_i)[:, 1]
        te_idx = df.loc[m_te].index
        out.loc[te_idx] = proba
    return out


