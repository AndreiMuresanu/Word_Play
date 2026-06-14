from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import pygame

from word_play.core import Render_Context, Render_Extractor, Render_Result, Render_Scene, Renderer, Renderer_State

from .draw import render_environment
from .extractors import default_pygame_extractors
from .runtime import configure_renderer, handle_entity_click, handle_prompt_panel_event, init_pygame_if_needed

if TYPE_CHECKING:
    from word_play.core import Environment

    from ..layout import Position_Layout_Adapter


class Pygame_Renderer(Renderer):
    """Concrete renderer that delegates drawing to pygame helpers."""

    def __init__(
        self,
        layout: "Position_Layout_Adapter",
        tile_size: int = 32,
        default_floor_sprite: str = "sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png",
        extractors: Sequence[Render_Extractor] | None = None,
    ):
        self.render_context: Render_Context = self.create_render_context()
        configure_renderer(
            self,
            layout=layout,
            tile_size=tile_size,
        )
        self.default_floor_sprite = default_floor_sprite
        self.extractors: list[Render_Extractor] = list(extractors or default_pygame_extractors(layout))

    def create_renderer_state(self) -> Renderer_State:
        state = Renderer_State()
        state.frame["world.floor_sprite"] = self.default_floor_sprite
        state.frame["ui.hud_visible"] = True
        return state

    def extract_scene(self, env: "Environment") -> Render_Scene:
        scene = Render_Scene()
        for extractor in self.extractors:
            extractor.extract(env, env.render_state, scene, self.render_context)
        return scene

    def present(self, env: "Environment") -> None:
        init_pygame_if_needed(self)
        render_environment(self, env, self.extract_scene(env))

    def handle_event(
        self,
        env: "Environment",
        event: pygame.event.Event,
        result: Render_Result | None = None,
    ) -> Render_Result:
        result = Render_Result() if result is None else result
        if handle_prompt_panel_event(self, event):
            return result
        if event.type == pygame.QUIT:
            result.quit_requested = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            result.quit_requested = True
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            result.reset_requested = True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            handle_entity_click(self, env, event.pos, button=event.button)
        return result

    def render(self, env: "Environment") -> Render_Result:
        self.present(env)

        result = Render_Result()
        for event in pygame.event.get():
            result = self.handle_event(env, event, result)
        return result
