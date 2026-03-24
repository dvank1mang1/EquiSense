"""Port for tabular equity models used by training, inference, and evaluation."""

from typing import Protocol

import numpy as np
import pandas as pd


class TabularEquityModel(Protocol):
    """
    Minimal surface for inference and metrics.

    Concrete classes: app.models.base.BaseMLModel and subclasses.
    Kept as Protocol so tests can stub without inheriting sklearn wrappers.
    """

    model_id: str
    feature_set: list[str]
    is_trained: bool

    def train(self, X: pd.DataFrame, y: pd.Series) -> None: ...

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray: ...

    def load(self) -> None: ...
