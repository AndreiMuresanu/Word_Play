from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from typing import Any, Literal, Mapping, Sequence


Chat_Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True, frozen=True)
class Chat_Message:
    role: Chat_Role
    content: str


def normalize_chat_messages(messages: Sequence[Chat_Message | Mapping[str, Any]]) -> list[dict[str, str]]:
    normalized_messages: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, Chat_Message):
            normalized_messages.append({"role": message.role, "content": message.content})
            continue

        role = str(message.get("role", "")).strip()
        content = str(message.get("content", ""))
        if not role:
            raise ValueError(f"Chat message is missing a role: {message}")
        normalized_messages.append({"role": role, "content": content})
    return normalized_messages


class Model(ABC):
    """
    Provider-agnostic model interface.

    Preferred method:
        - generate_chat(messages=[...])
        - provider-specific generate_chat_batch(...) when a model supports real batching

    Backward compatibility:
        - generate_text(input_text=...) remains available and maps to generate_chat.
        - generate_text_batch(input_texts=[...]) is a default threaded fallback.
    """

    def __init__(self, verbosity: int = 0) -> None:
        self.verbosity = verbosity

    @abstractmethod
    def generate_chat(
        self,
        messages: Sequence[Chat_Message | Mapping[str, Any]],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> str:
        pass

    def generate_chat_batch(
        self,
        messages_batch: Sequence[Sequence[Chat_Message | Mapping[str, Any]]],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> list[str]:
        # WARNING: this is a default implementation of batching. When model level or API batching
        #   is available, this method should be overwritten.

        if len(messages_batch) == 0:
            return []

        with ThreadPoolExecutor(max_workers=len(messages_batch)) as executor:
            return list(
                executor.map(
                    self.generate_chat,
                    messages_batch,
                    repeat(generation_config),
                    repeat(max_new_tokens),
                )
            )

    def generate_text(
        self,
        input_text: str | Sequence[str],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> str:
        if not isinstance(input_text, str):
            return self.generate_text_batch(input_text, generation_config, max_new_tokens)

        return self.generate_chat(
            messages=[Chat_Message(role="user", content=input_text)],
            generation_config=generation_config,
            max_new_tokens=max_new_tokens,
        )

    def generate_text_batch(
        self,
        input_texts: Sequence[str],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> list[str]:
        # WARNING: this is a default implementation of batching. When model level or API batching
        #   is available, this method should be overwritten.
        
        return self.generate_chat_batch(
            [[Chat_Message(role="user", content=input_text)] for input_text in input_texts],
            generation_config=generation_config,
            max_new_tokens=max_new_tokens,
        )

    def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:
        raise NotImplementedError()
