import numpy as np
import pandas as pd

from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

ALL_FEATURES = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES


class ModelD(BaseMLModel):
    """
    Model D — все признаки: технические + фундаментальные + sentiment.
    Алгоритм: XGBoost (основная модель).
    """

    model_id = "model_d"
    feature_set = ALL_FEATURES

    def __init__(self):
        super().__init__()
        from xgboost import XGBClassifier

        self.model = XGBClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss",
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
