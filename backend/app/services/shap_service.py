from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from app.contracts.features import FeatureStorePort
from app.domain.exceptions import FeatureDataMissingError, ModelArtifactMissingError
from app.domain.identifiers import ModelId
from app.explainability.shap_explainer import ShapExplainer
from app.models import get_model_class


class ShapExplanationOutcome:
    def __init__(
        self,
        ticker: str,
        model_id: str,
        features: list[dict],
        base_value: float,
        prediction: float,
        group_contributions: dict[str, float],
    ) -> None:
        self.ticker = ticker
        self.model_id = model_id
        self.features = features
        self.base_value = base_value
        self.prediction = prediction
        self.group_contributions = group_contributions


class ShapService:
    def __init__(self, features: FeatureStorePort) -> None:
        self._features = features

    async def explain(
        self,
        ticker: str,
        model_id: ModelId,
        top_n: int = 10,
        *,
        artifact_path: str | None = None,
    ) -> ShapExplanationOutcome:
        normalized = ticker.strip().upper()

        model_cls = get_model_class(model_id)
        instance = model_cls()

        try:
            instance.load(artifact_path)
        except FileNotFoundError as e:
            raise ModelArtifactMissingError(
                f"No trained artifact for {model_id.value}; run training first."
            ) from e

        def _build_data() -> tuple[pd.DataFrame, pd.DataFrame]:
            combined = self._features.build_combined(normalized)
            if combined.empty:
                raise FeatureDataMissingError(f"Empty combined features for {normalized}")
            missing = [c for c in instance.feature_set if c not in combined.columns]
            if missing:
                raise FeatureDataMissingError(
                    f"Missing columns for {instance.model_id}: {missing[:8]}"
                )
            return combined, combined.tail(1)

        combined, last_row = await asyncio.to_thread(_build_data)

        def _compute_shap() -> tuple[dict[str, float], float]:
            explainer = ShapExplainer(instance)
            explainer._build_explainer(combined)
            shap_vals = explainer.explain_single(last_row)
            base_val = explainer.base_value()
            return shap_vals, base_val, explainer

        shap_vals, base_val, explainer = await asyncio.to_thread(_compute_shap)

        top_features = explainer.get_top_features(shap_vals, top_n=top_n)
        group_contribs = explainer.group_contributions(shap_vals)

        prob_arr = instance.predict_proba(last_row)
        prediction = float(prob_arr[0, 1])

        return ShapExplanationOutcome(
            ticker=normalized,
            model_id=model_id.value,
            features=top_features,
            base_value=base_val,
            prediction=prediction,
            group_contributions=group_contribs,
        )
