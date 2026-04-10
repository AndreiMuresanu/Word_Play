from __future__ import annotations

from typing import Callable

from word_play.presets.models.model import Model
from word_play.presets.models.lazy import Lazy_Model_Handle


LLM_MODEL_REGISTRY: dict[str, Model] = {}


def register_model(model_key: str, model_or_loader: Model | Callable[[], Model]) -> None:
    if callable(model_or_loader):
        LLM_MODEL_REGISTRY[model_key] = Lazy_Model_Handle(model_or_loader)
    else:
        LLM_MODEL_REGISTRY[model_key] = model_or_loader


def resolve_registered_model(model_key: str) -> Model:
    if model_key not in LLM_MODEL_REGISTRY:
        raise KeyError(
            f"Model '{model_key}' not found in LLM_MODEL_REGISTRY. "
            f"Available keys: {list(LLM_MODEL_REGISTRY)}"
        )
    return LLM_MODEL_REGISTRY[model_key]
