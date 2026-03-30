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
        """Метрики: F1, ROC-AUC, PR-AUC, Brier, precision, recall."""
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )

        y_pred = self.predict(X)
        y_proba = self.predict_proba(X)[:, 1]
        out: dict[str, float] = {
            "f1": float(f1_score(y, y_pred)),
            "roc_auc": float(roc_auc_score(y, y_proba)),
            "precision": float(precision_score(y, y_pred)),
            "recall": float(recall_score(y, y_pred)),
        }
        try:
            out["brier"] = float(brier_score_loss(y, y_proba))
        except ValueError:
            out["brier"] = float("nan")
        try:
            out["pr_auc"] = float(average_precision_score(y, y_proba))
        except ValueError:
            out["pr_auc"] = float("nan")
        return out

    def save(self, artifact_path: str | Path | None = None) -> None:
        """Сохранить модель на диск."""
        target = Path(artifact_path) if artifact_path is not None else self.model_path
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, target)

    def load(self, artifact_path: str | Path | None = None) -> None:
        """Загрузить модель с диска."""
        target = Path(artifact_path) if artifact_path is not None else self.model_path
        if not target.exists():
            raise FileNotFoundError(f"Model file not found: {target}")
        self.model = joblib.load(target)
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
