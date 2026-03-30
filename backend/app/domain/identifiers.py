from enum import StrEnum


class ModelId(StrEnum):
    BASELINE_LR = "baseline_lr"
    MODEL_A = "model_a"
    MODEL_B = "model_b"
    MODEL_C = "model_c"
    MODEL_D = "model_d"
    MODEL_E = "model_e"
    MODEL_F = "model_f"


# Production rollout set (excludes baseline LR).
ROLLOUT_MODEL_IDS: tuple[ModelId, ...] = (
    ModelId.MODEL_A,
    ModelId.MODEL_B,
    ModelId.MODEL_C,
    ModelId.MODEL_D,
    ModelId.MODEL_E,
    ModelId.MODEL_F,
)


class FeatureSlice(StrEnum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    COMBINED = "combined"
