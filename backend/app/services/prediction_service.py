"""
Application service: orchestrates data + feature store + model for one prediction.

Routers stay thin; domain errors bubble up and are mapped to HTTP in the API layer.
"""

from __future__ import annotations

import asyncio

import pandas as pd

from app.contracts.data_providers import MarketDataProvider
from app.contracts.features import FeatureStorePort
from app.domain.exceptions import FeatureDataMissingError, ModelArtifactMissingError
from app.domain.identifiers import ModelId
from app.domain.prediction import PredictionOutcome


class PredictionService:
    def __init__(
        self,
        market: MarketDataProvider,
        features: FeatureStorePort,
    ) -> None:
        self._market = market
        self._features = features

    async def predict(self, ticker: str, model_id: ModelId) -> PredictionOutcome:
        """
        Run inference for latest available row.

        Pipeline: resolve model → load artifact → build_combined → last row → predict_proba → signal.
        Heavy steps run in asyncio.to_thread to avoid blocking the event loop.
        """
        from app.models import get_model_class

        normalized = ticker.strip().upper()
        model_cls = get_model_class(model_id)
        instance = model_cls()
        try:
            instance.load()
        except FileNotFoundError as e:
            raise ModelArtifactMissingError(
                f"No trained artifact for {model_id.value}; run training script first."
            ) from e

        def _load_last_row() -> pd.DataFrame:
            combined = self._features.build_combined(normalized)
            return combined.tail(1)

        try:
            X_last = await asyncio.to_thread(_load_last_row)
        except FeatureDataMissingError:
            raise

        if X_last.empty:
            raise FeatureDataMissingError(f"Empty combined feature frame for {normalized}")

        missing = [c for c in instance.feature_set if c not in X_last.columns]
        if missing:
            preview = missing[:8]
            suffix = "..." if len(missing) > 8 else ""
            raise FeatureDataMissingError(
                f"Missing feature columns for {instance.model_id}: {preview}{suffix}"
            )

        X_model = X_last[instance.feature_set]

        def _positive_class_proba() -> float:
            arr = instance.predict_proba(X_model)
            return float(arr[0, 1])

        probability = await asyncio.to_thread(_positive_class_proba)
        signal = instance.get_signal(probability)
        confidence = abs(probability - 0.5) * 2.0

        as_of = X_last["date"].iloc[0] if "date" in X_last.columns else None
        as_of_s = (
            as_of.isoformat()
            if hasattr(as_of, "isoformat")
            else (str(as_of) if as_of is not None else None)
        )

        _ = self._market  # будущий fallback: пересчёт фич из raw OHLCV при отсутствии combined

        return PredictionOutcome(
            ticker=normalized,
            model_id=model_id.value,
            probability=probability,
            signal=signal,
            confidence=confidence,
            explanation={
                "stage": "inference_complete",
                "as_of_date": as_of_s,
            },
        )
