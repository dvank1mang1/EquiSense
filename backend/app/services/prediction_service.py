"""
Application service: orchestrates data + feature store + model for one prediction.

Routers stay thin; domain errors bubble up and are mapped to HTTP in the API layer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from app.contracts.data_providers import MarketDataProvider
from app.contracts.features import FeatureStorePort
from app.data.persistence import fundamentals_json_path, ohlcv_parquet_path
from app.domain.exceptions import FeatureDataMissingError, ModelArtifactMissingError
from app.domain.identifiers import ModelId
from app.domain.prediction import PredictionOutcome, PredictionReadinessOutcome


def _resolve_feature_set(instance: object) -> list[str]:
    expected = getattr(instance, "expected_feature_set", None)
    if callable(expected):
        out = expected()
        if isinstance(out, list):
            return [str(v) for v in out]
    raw = getattr(instance, "feature_set", [])
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return []


def _validate_feature_columns(instance: object, frame: pd.DataFrame) -> list[str]:
    checker = getattr(instance, "ensure_feature_columns", None)
    if callable(checker):
        checker(frame)
        return _resolve_feature_set(instance)
    required = _resolve_feature_set(instance)
    missing = [c for c in required if c not in frame.columns]
    if missing:
        preview = missing[:8]
        suffix = "..." if len(missing) > 8 else ""
        raise ValueError(f"Missing feature columns for model: {preview}{suffix}")
    return required


class PredictionService:
    def __init__(
        self,
        market: MarketDataProvider,
        features: FeatureStorePort,
    ) -> None:
        self._market = market
        self._features = features

    async def readiness(
        self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
    ) -> PredictionReadinessOutcome:
        """Check whether inference dependencies are present and consistent."""
        from app.models import get_model_class

        sym = ticker.strip().upper()
        model_cls = get_model_class(model_id)
        instance = model_cls()

        checks: dict[str, dict[str, str | bool]] = {}

        raw_ohlcv = ohlcv_parquet_path(sym)
        checks["raw_ohlcv"] = {
            "ok": raw_ohlcv.exists(),
            "detail": str(raw_ohlcv),
        }
        raw_fund = fundamentals_json_path(sym)
        checks["raw_fundamentals"] = {
            "ok": raw_fund.exists(),
            "detail": str(raw_fund),
        }

        tech_exists = self._features.exists(sym, "technical")
        fund_exists = self._features.exists(sym, "fundamental")
        checks["processed_technical"] = {
            "ok": tech_exists,
            "detail": str(self._features.path_for(sym, "technical")),
        }
        checks["processed_fundamental"] = {
            "ok": fund_exists,
            "detail": str(self._features.path_for(sym, "fundamental")),
        }

        model_path = Path(artifact_path) if artifact_path else Path(instance.model_path)
        checks["model_artifact"] = {
            "ok": model_path.exists(),
            "detail": str(model_path),
        }

        try:
            combined = await asyncio.to_thread(self._features.build_combined, sym)
            if combined.empty:
                checks["combined_features"] = {"ok": False, "detail": "combined features are empty"}
            else:
                try:
                    _validate_feature_columns(instance, combined)
                except ValueError as e:
                    checks["combined_features"] = {
                        "ok": False,
                        "detail": str(e),
                    }
                else:
                    checks["combined_features"] = {
                        "ok": True,
                        "detail": f"rows={len(combined)}",
                    }
        except Exception as e:  # noqa: BLE001
            checks["combined_features"] = {"ok": False, "detail": str(e)}

        required = (
            "processed_technical",
            "model_artifact",
            "combined_features",
        )
        ready = all(bool(checks[k]["ok"]) for k in required)
        return PredictionReadinessOutcome(
            ticker=sym,
            model_id=model_id.value,
            ready=ready,
            checks=checks,
        )

    async def predict(
        self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
    ) -> PredictionOutcome:
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
            instance.load(artifact_path)
        except FileNotFoundError as e:
            raise ModelArtifactMissingError(
                f"No trained artifact for {model_id.value}. "
                f"POST /api/v1/models/{model_id.value}/train with JSON {{\"ticker\":\"AAPL\"}}, "
                "poll GET …/train/{{run_id}} until status completed, then call predict again "
                f"(or copy weights to {instance.model_path})."
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

        try:
            model_features = _validate_feature_columns(instance, X_last)
        except ValueError as e:
            raise FeatureDataMissingError(str(e)) from e
        X_model = X_last[model_features]

        def _positive_class_proba() -> float:
            arr = instance.predict_proba(X_model)
            return float(arr[0, 1])

        probability = await asyncio.to_thread(_positive_class_proba)
        signal = instance.get_signal(probability)
        confidence = abs(probability - 0.5) * 2.0

        as_of = X_last["date"].iloc[0] if "date" in X_last.columns else None
        if as_of is None:
            as_of_s: str | None = None
        else:
            iso = getattr(as_of, "isoformat", None)
            as_of_s = str(iso()) if callable(iso) else str(as_of)

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
