from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Environment


@dataclass(slots=True)
class Human_Text_Request:
    observation_text: str
    initial_text: str = ""
    prompt: str = "> "

    def prompt_text(self) -> str:
        return self.prompt


class Human_IO(ABC):
    @abstractmethod
    def notify(self, text: str, *, env: "Environment" | None = None) -> None:
        pass

    @abstractmethod
    def request_text(
        self,
        request: Human_Text_Request,
        *,
        env: "Environment" | None = None,
    ) -> str:
        pass


class Terminal_Human_IO(Human_IO):
    def notify(self, text: str, *, env: "Environment" | None = None) -> None:
        del env
        if text:
            print(text)

    def request_text(
        self,
        request: Human_Text_Request,
        *,
        env: "Environment" | None = None,
    ) -> str:
        del env
        observation_text = request.observation_text.strip()
        if observation_text:
            print(observation_text)
        return input(request.prompt_text())


class Auto_Human_IO(Human_IO):
    def __init__(self, terminal_io: Human_IO | None = None):
        self.terminal_io = terminal_io or Terminal_Human_IO()

    def _delegate(self, env: "Environment" | None) -> Human_IO:
        if env is None or getattr(env, "renderer", None) is None:
            return self.terminal_io

        try:
            from word_play.presets.renderers.pygame_renderer.human_io import Pygame_Overlay_Human_IO
            from word_play.presets.renderers.pygame_renderer.renderer import Pygame_Renderer
        except Exception:
            return self.terminal_io

        if not isinstance(env.renderer, Pygame_Renderer):
            return self.terminal_io

        overlay_io = getattr(env.renderer, "_human_overlay_io", None)
        if overlay_io is None:
            overlay_io = Pygame_Overlay_Human_IO(fallback=self.terminal_io)
            env.renderer._human_overlay_io = overlay_io
        return overlay_io

    def notify(self, text: str, *, env: "Environment" | None = None) -> None:
        self._delegate(env).notify(text, env=env)

    def request_text(
        self,
        request: Human_Text_Request,
        *,
        env: "Environment" | None = None,
    ) -> str:
        return self._delegate(env).request_text(
            request,
            env=env,
        )
