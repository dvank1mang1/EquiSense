import numpy as np
import pandas as pd

from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

ALL_FEATURES = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES


class ModelGRanker(BaseMLModel):
    """
    LightGBM ranker (LambdaMART-style objective) for cross-sectional stock ranking.
    """

    model_id = "model_g_ranker"
    feature_set = ALL_FEATURES

    def __init__(self):
        super().__init__()
        from lightgbm import LGBMRanker

        self.model = LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=300,
            num_leaves=63,
            learning_rate=0.05,
            random_state=42,
        )
        self.is_ranking_model = True

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        raise NotImplementedError("Use TrainingService ranking path with date-based group sizes")

    def fit_ranker(self, X: pd.DataFrame, y: pd.Series, *, group: list[int]) -> None:
        self.model.fit(X[self.feature_set], y, group=group)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        scores = np.asarray(self.model.predict(X[self.feature_set]), dtype=float)
        # Map unbounded ranking score to pseudo-probability for compatibility.
        probs = 1.0 / (1.0 + np.exp(-scores))
        return np.column_stack([1.0 - probs, probs])
