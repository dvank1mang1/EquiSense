from enum import StrEnum


class ModelId(StrEnum):
    BASELINE_LR = "baseline_lr"
    MODEL_A = "model_a"
    MODEL_B = "model_b"
    MODEL_C = "model_c"
    MODEL_D = "model_d"


class FeatureSlice(StrEnum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    COMBINED = "combined"
