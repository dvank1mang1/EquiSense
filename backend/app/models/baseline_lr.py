from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.features.constants import TECHNICAL_FEATURES
from app.models.base import BaseMLModel

__all__ = ["BaselineLRModel"]


class BaselineLRModel(BaseMLModel):
    model_id = "baseline_lr"
    feature_set = TECHNICAL_FEATURES

    def __init__(self) -> None:
        super().__init__()
        self.model: Pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "lr",
                    LogisticRegression(
                        max_iter=2000,
                        random_state=42,
                        class_weight="balanced",
                        solver="lbfgs",
                        C=1.0,
                    ),
                ),
            ]
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.model.fit(X[self.feature_set], y)
        self.is_trained = True

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_set])
