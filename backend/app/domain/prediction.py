"""Domain outcome for a single prediction — API layer maps this to Pydantic response models."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PredictionOutcome:
    """Result of one inference pass (before HTTP serialization)."""

    ticker: str
    model_id: str
    probability: float | None
    signal: str | None
    confidence: float | None
    explanation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PredictionReadinessOutcome:
    """Readiness snapshot for one ticker + model inference path."""

    ticker: str
    model_id: str
    ready: bool
    checks: dict[str, dict[str, Any]]
