import numpy as np
import pandas as pd

from app.features.constants import SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

ALL_FEATURES = TECHNICAL_FEATURES + SENTIMENT_FEATURES


class ModelC(BaseMLModel):
    """
    Model C — технические + sentiment (новости через FinBERT).
    Алгоритм: Random Forest.
    """

    model_id = "model_c"
    feature_set = ALL_FEATURES

    def __init__(self):
        super().__init__()
        from sklearn.ensemble import RandomForestClassifier

        self.model = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            random_state=42,
            n_jobs=-1,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
