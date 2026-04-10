from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from word_play.presets.models.model import Chat_Message, Model


class Lazy_Model_Handle(Model):
    """
    Defers model construction until first generation call.
    """

    def __init__(self, loader: Callable[[], Model], verbosity: int = 0):
        super().__init__(verbosity=verbosity)
        self.loader = loader
        self._model: Model | None = None

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = self.loader()
        return self._model

    def generate_chat(
        self,
        messages: Sequence[Chat_Message | Mapping[str, Any]],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> str:
        return self.model.generate_chat(
            messages, generation_config=generation_config, max_new_tokens=max_new_tokens
        )

    def cond_logP(self, inputs, targets):
        return self.model.cond_logP(inputs, targets)
