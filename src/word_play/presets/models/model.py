from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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

    Backward compatibility:
        - generate_text(input_text=...) remains available and maps to generate_chat.
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

    def generate_text(
        self,
        input_text: str | list[str],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> str:
        if type(input_text) is str:
            raise NotImplementedError("Batched inputs are not supported yet.")
        return self.generate_chat(
            messages=[Chat_Message(role="user", content=input_text)],
            generation_config=generation_config,
            max_new_tokens=max_new_tokens,
        )

    def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:
        raise NotImplementedError()
