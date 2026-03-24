from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.core.config import settings


class BaseMLModel(ABC):
    """
    Базовый класс для всех ML-моделей.
    Определяет общий интерфейс: train, predict, evaluate, save, load.
    """

    model_id: str
    feature_set: list[str]

    def __init__(self):
        self.model = None
        self.is_trained = False
        self.model_path = Path(settings.model_dir) / f"{self.model_id}.joblib"

    @abstractmethod
    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Обучить модель."""

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Вернуть вероятности классов."""

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Вернуть бинарные предсказания."""
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Рассчитать метрики: F1, ROC-AUC, Precision, Recall."""
        from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

        y_pred = self.predict(X)
        y_proba = self.predict_proba(X)[:, 1]
        return {
            "f1": f1_score(y, y_pred),
            "roc_auc": roc_auc_score(y, y_proba),
            "precision": precision_score(y, y_pred),
            "recall": recall_score(y, y_pred),
        }

    def save(self) -> None:
        """Сохранить модель на диск."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, self.model_path)

    def load(self) -> None:
        """Загрузить модель с диска."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        self.model = joblib.load(self.model_path)
        self.is_trained = True

    def get_signal(self, probability: float) -> str:
        """Конвертировать вероятность в торговый сигнал."""
        if probability >= 0.70:
            return "Strong Buy"
        elif probability >= 0.55:
            return "Buy"
        elif probability >= 0.45:
            return "Hold"
        else:
            return "Sell"
