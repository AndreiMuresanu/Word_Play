from __future__ import annotations

import pygame

from word_play.presets.human_io import Human_IO, Human_Text_Request, Terminal_Human_IO

from .runtime import (
    pygame_runtime,
    scroll_prompt_lines,
    set_prompt_scroll_end,
    set_prompt_scroll_home,
)


class Pygame_Overlay_Human_IO(Human_IO):
    MAX_HISTORY_BLOCKS = 240

    def __init__(self, fallback: Human_IO | None = None):
        self.fallback = fallback or Terminal_Human_IO()

    def _append_history(self, renderer, text: str) -> None:
        prompt_state = pygame_runtime(renderer).prompt
        if text:
            prompt_state.history_blocks.append(text)
        else:
            prompt_state.history_blocks.append("")
        if len(prompt_state.history_blocks) > self.MAX_HISTORY_BLOCKS:
            prompt_state.history_blocks = prompt_state.history_blocks[-self.MAX_HISTORY_BLOCKS :]

    def _renderer_for_env(self, env):
        renderer = None if env is None else getattr(env, "renderer", None)
        if renderer is None or not hasattr(renderer, "present") or not hasattr(renderer, "handle_event"):
            return None
        return renderer

    def notify(self, text: str, *, env=None) -> None:
        renderer = self._renderer_for_env(env)
        if renderer is None:
            self.fallback.notify(text, env=env)
            return

        self._append_history(renderer, text)
        set_prompt_scroll_end(renderer)

    def request_text(
        self,
        request: Human_Text_Request,
        *,
        env=None,
    ) -> str:
        renderer = self._renderer_for_env(env)
        if renderer is None:
            return self.fallback.request_text(
                request,
                env=env,
            )

        prompt_state = pygame_runtime(renderer).prompt
        prompt_state.active = True
        prompt_state.title = "Human IO"
        prompt_state.body = request.observation_text
        prompt_state.prompt = request.prompt_text()
        prompt_state.input_text = request.initial_text
        if prompt_state.body:
            self._append_history(renderer, prompt_state.body)
        set_prompt_scroll_end(renderer)

        clock = pygame.time.Clock()
        renderer.present(env)
        pygame.key.start_text_input()

        try:
            while True:
                renderer.present(env)
                result = None

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise RuntimeError("Renderer window closed while waiting for human input.")

                    if event.type == pygame.TEXTINPUT:
                        prompt_state.input_text += event.text
                        continue

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN:
                            submitted = prompt_state.input_text
                            self._append_history(renderer, f"{prompt_state.prompt}{submitted}")
                            self._append_history(renderer, "")
                            set_prompt_scroll_end(renderer)
                            prompt_state.input_text = ""
                            return submitted
                        if event.key == pygame.K_BACKSPACE:
                            prompt_state.input_text = prompt_state.input_text[:-1]
                            continue
                        if event.key == pygame.K_ESCAPE:
                            raise RuntimeError("Human input cancelled from the renderer.")
                        if event.key == pygame.K_PAGEUP:
                            scroll_prompt_lines(renderer, -12)
                            continue
                        if event.key == pygame.K_PAGEDOWN:
                            scroll_prompt_lines(renderer, 12)
                            continue
                        if event.key == pygame.K_HOME:
                            set_prompt_scroll_home(renderer)
                            continue
                        if event.key == pygame.K_END:
                            set_prompt_scroll_end(renderer)
                            continue
                        if event.key == pygame.K_UP:
                            scroll_prompt_lines(renderer, -1)
                            continue
                        if event.key == pygame.K_DOWN:
                            scroll_prompt_lines(renderer, 1)
                            continue
                        continue

                    result = renderer.handle_event(env, event, result)
                    if result.quit_requested:
                        raise RuntimeError("Renderer window closed while waiting for human input.")

                clock.tick(30)
        finally:
            pygame.key.stop_text_input()
            prompt_state.active = False
            prompt_state.title = ""
            prompt_state.body = ""
            prompt_state.prompt = "> "
            prompt_state.input_text = ""
