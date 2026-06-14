from __future__ import annotations

from typing import Any, Mapping, Sequence

from word_play.presets.human_io import Human_IO, Human_Text_Request, Terminal_Human_IO
from word_play.presets.models.model import Chat_Message, Model, normalize_chat_messages


class Human_Model(Model):
    """
    Replaces the LLM with a human typing responses.
    The human sees the exact same prompt the LLM would receive.
    """

    def __init__(self, io: Human_IO | None = None):
        self.io = io or Terminal_Human_IO()

    def generate_chat(
        self,
        messages: Sequence[Chat_Message | Mapping[str, Any]],
        generation_config: Mapping[str, Any] | None = None,
        max_new_tokens: int | None = None,
    ) -> str:
        del generation_config, max_new_tokens
        normalized = normalize_chat_messages(messages)
        rendered = "\n".join(f"[{message['role']}] {message['content']}" for message in normalized)
        return self.io.request_text(
            Human_Text_Request(
                observation_text=rendered,
            )
        )
