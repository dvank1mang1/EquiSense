from __future__ import annotations

import numpy as np
import pandas as pd

from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES
from app.models.base import BaseMLModel

_FEATURE_GROUPS: dict[str, list[str]] = {
    "technical": TECHNICAL_FEATURES,
    "fundamental": FUNDAMENTAL_FEATURES,
    "news": SENTIMENT_FEATURES,
}


def _extract_inner_model(model: object) -> object:
    try:
        from sklearn.pipeline import Pipeline
        if isinstance(model, Pipeline):
            return model.named_steps.get("lr") or model.steps[-1][1]
    except ImportError:
        pass
    return model


def _is_tree_model(inner: object) -> bool:
    try:
        from xgboost import XGBClassifier
        if isinstance(inner, XGBClassifier):
            return True
    except (ImportError, OSError):
        pass
    try:
        from lightgbm import LGBMClassifier
        if isinstance(inner, LGBMClassifier):
            return True
    except (ImportError, OSError):
        pass
    try:
        from sklearn.ensemble import RandomForestClassifier
        if isinstance(inner, RandomForestClassifier):
            return True
    except (ImportError, OSError):
        pass
    return False


def _is_linear_model(inner: object) -> bool:
    try:
        from sklearn.linear_model import LogisticRegression
        return isinstance(inner, LogisticRegression)
    except ImportError:
        return False


class ShapExplainer:
    def __init__(self, model: BaseMLModel) -> None:
        self._model = model
        self._explainer = None
        self._background: pd.DataFrame | None = None
        self._feature_set: list[str] = model.feature_set

    def _build_explainer(self, X_background: pd.DataFrame) -> None:
        import shap

        sample_size = min(100, len(X_background))
        bg_df = X_background[self._feature_set].sample(sample_size, random_state=42)
        self._background = bg_df

        inner = _extract_inner_model(self._model.model)

        if _is_tree_model(inner):
            self._explainer = shap.TreeExplainer(inner, bg_df.values)
        elif _is_linear_model(inner):
            try:
                from sklearn.pipeline import Pipeline
                if isinstance(self._model.model, Pipeline):
                    bg_transformed = self._model.model.named_steps["scaler"].transform(bg_df)
                    self._explainer = shap.LinearExplainer(inner, bg_transformed)
                else:
                    self._explainer = shap.LinearExplainer(inner, bg_df.values)
            except Exception:
                self._explainer = shap.LinearExplainer(inner, bg_df.values)
        else:
            self._explainer = shap.Explainer(self._model.model, bg_df.values)

    def explain_single(self, X_row: pd.DataFrame) -> dict[str, float]:
        if self._explainer is None:
            raise RuntimeError("Call _build_explainer before explain_single")

        X_feat_df = X_row[self._feature_set]

        try:
            from sklearn.pipeline import Pipeline
            if isinstance(self._model.model, Pipeline) and _is_linear_model(
                _extract_inner_model(self._model.model)
            ):
                X_feat = self._model.model.named_steps["scaler"].transform(X_feat_df)
            else:
                X_feat = X_feat_df.values
        except Exception:
            X_feat = X_feat_df.values

        shap_vals = self._explainer.shap_values(X_feat)

        if isinstance(shap_vals, list):
            arr = np.array(shap_vals[1]).flatten()
        else:
            arr = np.array(shap_vals).flatten()
            if arr.ndim == 2:
                arr = arr[:, 1] if arr.shape[1] == 2 else arr.flatten()

        return dict(zip(self._feature_set, arr.tolist()))

    def explain_batch(self, X: pd.DataFrame) -> pd.DataFrame:
        if self._explainer is None:
            raise RuntimeError("Call _build_explainer before explain_batch")

        X_feat_df = X[self._feature_set]

        try:
            from sklearn.pipeline import Pipeline
            if isinstance(self._model.model, Pipeline) and _is_linear_model(
                _extract_inner_model(self._model.model)
            ):
                X_feat = self._model.model.named_steps["scaler"].transform(X_feat_df)
            else:
                X_feat = X_feat_df.values
        except Exception:
            X_feat = X_feat_df.values

        shap_vals = self._explainer.shap_values(X_feat)

        if isinstance(shap_vals, list):
            arr = np.array(shap_vals[1])
        else:
            arr = np.array(shap_vals)
            if arr.ndim == 3:
                arr = arr[:, :, 1]

        return pd.DataFrame(arr, columns=self._feature_set, index=X.index)

    def group_contributions(self, shap_values: dict[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for group_name, group_features in _FEATURE_GROUPS.items():
            total = sum(abs(shap_values.get(f, 0.0)) for f in group_features)
            result[group_name] = round(total, 6)
        return result

    def get_top_features(self, shap_values: dict[str, float], top_n: int = 10) -> list[dict]:
        sorted_features = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
        return [
            {"name": name, "shap_value": round(val, 6)}
            for name, val in sorted_features[:top_n]
        ]

    def base_value(self) -> float:
        if self._explainer is None:
            return 0.0
        ev = getattr(self._explainer, "expected_value", 0.0)
        if isinstance(ev, (list, np.ndarray)):
            arr = np.asarray(ev).flatten()
            return float(arr[1]) if len(arr) > 1 else float(arr[0])
        return float(ev)
