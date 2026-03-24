from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Signal(StrEnum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class FeatureContribution(BaseModel):
    technical: float
    fundamental: float
    news: float


class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ticker: str
    model: str
    signal: Signal | None = None
    probability: float | None = None
    confidence: float | None = None
    # Pipeline status, SHAP summary, or bucketed contributions (see FeatureContribution when stable)
    explanation: dict[str, Any] | None = None


class ModelMetrics(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    signal: Signal | None = None
    probability: float | None = None
    f1: float | None = None
    roc_auc: float | None = None


class ModelComparisonResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ticker: str
    model_a: ModelMetrics
    model_b: ModelMetrics
    model_c: ModelMetrics
    model_d: ModelMetrics


class ShapFeature(BaseModel):
    name: str
    value: float
    shap_value: float


class ShapExplanation(BaseModel):
    ticker: str
    model: str
    features: list[ShapFeature]
    base_value: float
    prediction: float


class ReadinessCheck(BaseModel):
    ok: bool
    detail: str


class EnsureReadyResponse(BaseModel):
    ticker: str
    model: str
    before_ready: bool
    after_ready: bool
    changed: bool
    run_id: str
    status_path: str
    lineage_path: str
    checks_before: dict[str, ReadinessCheck]
    checks_after: dict[str, ReadinessCheck]


class PredictionStatusResponse(BaseModel):
    ticker: str
    model: str
    ready: bool
    recommended_action: str
    checks: dict[str, ReadinessCheck]
    freshness: dict[str, dict[str, object]]
    latest_job: dict[str, object] | None = None


class PredictionReadinessResponse(BaseModel):
    ticker: str
    model: str
    ready: bool
    checks: dict[str, ReadinessCheck]
