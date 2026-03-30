import numpy as np
import pandas as pd

from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

ALL_FEATURES = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES

__all__ = ["ModelE", "ALL_FEATURES"]


class ModelE(BaseMLModel):
    """
    Model E — полный набор признаков (tech + fundamental + sentiment).
    Алгоритм: HistGradientBoosting (sklearn), устойчив к шуму на табличных данных.
    """

    model_id = "model_e"
    feature_set = ALL_FEATURES

    def __init__(self) -> None:
        super().__init__()
        from sklearn.ensemble import HistGradientBoostingClassifier

        self.model = HistGradientBoostingClassifier(
            max_iter=450,
            max_depth=10,
            learning_rate=0.045,
            l2_regularization=0.06,
            min_samples_leaf=24,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.12,
            n_iter_no_change=30,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
