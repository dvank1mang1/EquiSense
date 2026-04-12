import numpy as np
import pandas as pd

from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

ALL_FEATURES = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES

__all__ = ["ModelF", "ALL_FEATURES"]


class ModelF(BaseMLModel):
    """
    Model F — полный набор признаков.
    Алгоритм: soft-voting ансамбль XGBoost + LightGBM (разные индуктивные смещения).
    """

    model_id = "model_f"
    feature_set = ALL_FEATURES

    def __init__(self) -> None:
        super().__init__()
        from lightgbm import LGBMClassifier
        from sklearn.ensemble import VotingClassifier
        from xgboost import XGBClassifier

        xgb = XGBClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            random_state=42,
            eval_metric="logloss",
            n_jobs=-1,
        )
        lgb = LGBMClassifier(
            n_estimators=500,
            max_depth=-1,
            num_leaves=48,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_samples=24,
            random_state=42,
            n_jobs=-1,
            verbosity=-1,
        )
        self.model = VotingClassifier(
            estimators=[("xgb", xgb), ("lgb", lgb)],
            voting="soft",
            weights=[1, 1],
            n_jobs=-1,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
