import pandas as pd
import numpy as np
from app.models.model_a import TECHNICAL_FEATURES
from app.models.base import BaseMLModel

FUNDAMENTAL_FEATURES = [
    "pe_ratio", "eps", "revenue_growth", "roe", "debt_to_equity",
]

ALL_FEATURES = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES


class ModelB(BaseMLModel):
    """
    Model B — технические + фундаментальные признаки.
    Алгоритм: LightGBM.
    """

    model_id = "model_b"
    feature_set = ALL_FEATURES

    def __init__(self):
        super().__init__()
        from lightgbm import LGBMClassifier
        self.model = LGBMClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
