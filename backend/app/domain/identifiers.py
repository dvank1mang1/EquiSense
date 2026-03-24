"""Domain identifiers — avoid stringly-typed model and feature names across layers."""

from enum import StrEnum


class ModelId(StrEnum):
    """Registered equity models (Plan.md: A–D feature compositions)."""

    MODEL_A = "model_a"
    MODEL_B = "model_b"
    MODEL_C = "model_c"
    MODEL_D = "model_d"


class FeatureSlice(StrEnum):
    """Logical partitions of the feature store (technical / fundamental / sentiment / joined)."""

    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    COMBINED = "combined"
