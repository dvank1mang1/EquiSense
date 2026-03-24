import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from app.features.constants import TECHNICAL_FEATURES
from app.models.base import BaseMLModel

__all__ = ["ModelA", "TECHNICAL_FEATURES"]


class ModelA(BaseMLModel):
    """
    Model A — только технические признаки.
    Алгоритм: XGBoost.
    """

    model_id = "model_a"
    feature_set = TECHNICAL_FEATURES

    def __init__(self):
        super().__init__()
        from xgboost import XGBClassifier
        self.model = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            random_state=42,
            eval_metric="logloss",
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
