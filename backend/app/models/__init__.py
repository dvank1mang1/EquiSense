from app.domain.exceptions import UnknownModelError
from app.domain.identifiers import ModelId
from app.models.base import BaseMLModel
from app.models.model_a import ModelA
from app.models.model_b import ModelB
from app.models.model_c import ModelC
from app.models.model_d import ModelD

MODEL_REGISTRY: dict[ModelId, type[BaseMLModel]] = {
    ModelId.MODEL_A: ModelA,
    ModelId.MODEL_B: ModelB,
    ModelId.MODEL_C: ModelC,
    ModelId.MODEL_D: ModelD,
}


def get_model_class(model_id: str | ModelId) -> type[BaseMLModel]:
    """Resolve a registered model; raises UnknownModelError for bad ids."""
    try:
        mid = model_id if isinstance(model_id, ModelId) else ModelId(model_id)
    except ValueError as e:
        raise UnknownModelError(f"Unknown model id: {model_id!r}") from e
    if mid not in MODEL_REGISTRY:
        raise UnknownModelError(f"Unknown model id: {model_id!r}")
    return MODEL_REGISTRY[mid]


__all__ = [
    "MODEL_REGISTRY",
    "BaseMLModel",
    "ModelA",
    "ModelB",
    "ModelC",
    "ModelD",
    "get_model_class",
]
