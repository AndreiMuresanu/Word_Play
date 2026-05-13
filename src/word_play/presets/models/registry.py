from __future__ import annotations

from typing import Any

from word_play.presets.models.model import Model


class Model_Registry:
    """
    Central registry for models.

    Models are registered as specs (class + kwargs) and constructed lazily
    on first resolve. Every call to resolve() with the same key returns the
    same instance, so any number of agents can share one model object with
    no duplication.

    Usage:
        # register once before building any agents
        LLM_MODEL_REGISTRY.register("main", OpenRouter_Model,
            model_name="qwen/qwen3-0.6b-04-28:free",
            system_prompt="...",
        )

        # agents hold only the key string
        # model is constructed once on first resolve, shared after that
        model = LLM_MODEL_REGISTRY.resolve("main")
    """

    def __init__(self) -> None:
        self._specs: dict[str, tuple[type[Model], dict[str, Any]]] = {}
        self._instances: dict[str, Model] = {}

    def register(self, key: str, model_class: type[Model], **kwargs: Any) -> None:
        """
        Register a model spec. The model is not constructed until resolve() is
        first called for this key.
        """
        if key in self._instances:
            raise ValueError(
                f"Model '{key}' is already loaded. Call unload('{key}') before re-registering."
            )
        self._specs[key] = (model_class, kwargs)

    def resolve(self, key: str) -> Model:
        """
        Return the model for this key, constructing it on first call.
        Subsequent calls return the same instance.
        """
        if key not in self._instances:
            if key not in self._specs:
                raise KeyError(
                    f"No model registered under '{key}'. "
                    f"Registered keys: {list(self._specs)}"
                )
            model_class, kwargs = self._specs[key]
            self._instances[key] = model_class(**kwargs)
        return self._instances[key]

    def unload(self, key: str) -> None:
        """
        Remove the constructed instance from memory.
        The spec is kept, so the model can be re-loaded by calling resolve() again.
        Useful for freeing GPU memory when switching between local models.
        """
        self._instances.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._specs


LLM_MODEL_REGISTRY = Model_Registry()


def register_model(key: str, model_class: type[Model], **kwargs: Any) -> None:
    LLM_MODEL_REGISTRY.register(key, model_class, **kwargs)


def resolve_registered_model(key: str) -> Model:
    return LLM_MODEL_REGISTRY.resolve(key)
