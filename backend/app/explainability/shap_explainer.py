import shap
import pandas as pd
import numpy as np
from app.models.base import BaseMLModel


class ShapExplainer:
    """
    Объясняет предсказания ML-моделей через SHAP.

    Поддерживает:
        - TreeExplainer (XGBoost, LightGBM, Random Forest)
        - LinearExplainer (Logistic Regression)

    Выходные данные:
        - shap_values: вклад каждого признака в предсказание
        - base_value: базовое значение (prior probability)
        - waterfall chart данные
        - группированный вклад по категориям (technical / fundamental / news)
    """

    def __init__(self, model: BaseMLModel):
        self.model = model
        self._explainer = None

    def _build_explainer(self, X_background: pd.DataFrame) -> None:
        """Инициализировать SHAP explainer на фоновых данных."""
        raise NotImplementedError

    def explain_single(self, X_row: pd.DataFrame) -> dict:
        """
        Объяснить одно предсказание.

        Returns:
            dict: {feature_name: shap_value, ...}
        """
        raise NotImplementedError

    def explain_batch(self, X: pd.DataFrame) -> pd.DataFrame:
        """Объяснить батч предсказаний."""
        raise NotImplementedError

    def group_contributions(self, shap_values: dict) -> dict:
        """
        Сгруппировать SHAP values по категориям признаков.

        Returns:
            {"technical": float, "fundamental": float, "news": float}
        """
        raise NotImplementedError

    def get_top_features(self, shap_values: dict, top_n: int = 10) -> list[dict]:
        """Вернуть топ-N наиболее важных признаков по |SHAP|."""
        raise NotImplementedError
