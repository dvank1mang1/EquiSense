from app.models.model_a import ModelA
from app.models.model_b import ModelB
from app.models.model_c import ModelC
from app.models.model_d import ModelD

MODEL_REGISTRY: dict = {
    "model_a": ModelA,
    "model_b": ModelB,
    "model_c": ModelC,
    "model_d": ModelD,
}

__all__ = ["ModelA", "ModelB", "ModelC", "ModelD", "MODEL_REGISTRY"]
