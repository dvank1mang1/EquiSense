from pydantic import BaseModel
from typing import Optional
from enum import Enum


class Signal(str, Enum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class FeatureContribution(BaseModel):
    technical: float
    fundamental: float
    news: float


class PredictionResponse(BaseModel):
    ticker: str
    model: str
    signal: Optional[Signal] = None
    probability: Optional[float] = None
    confidence: Optional[float] = None
    explanation: Optional[FeatureContribution] = None


class ModelMetrics(BaseModel):
    model_id: str
    signal: Optional[Signal] = None
    probability: Optional[float] = None
    f1: Optional[float] = None
    roc_auc: Optional[float] = None


class ModelComparisonResponse(BaseModel):
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
