from __future__ import annotations

from abc import ABC, abstractmethod


class Model(ABC):
    """
    Minimal provider-agnostic text generation interface.
    """

    def __init__(self, verbosity: int = 0) -> None:
        self.verbosity = verbosity

    @abstractmethod
    def generate_text(
        self,
        input_text: str | list[str],
        generation_config=None,
        max_new_tokens=None,
    ):
        pass

    def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:
        raise NotImplementedError()
