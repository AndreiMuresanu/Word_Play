from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from word_play.core import Render_Result, Renderer, Renderer_State

from .draw import render_environment
from .runtime import configure_renderer, handle_entity_click, init_pygame_if_needed

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
    ):
        configure_renderer(
            self,
            layout=layout,
            tile_size=tile_size,
        )
        self.default_floor_sprite = default_floor_sprite

    def create_renderer_state(self) -> Renderer_State:
        state = Renderer_State()
        state.set_value("world.floor_sprite", self.default_floor_sprite)
        state.set_value("ui.hud_visible", True)
        return state

    def render(self, env: "Environment") -> Render_Result:
        init_pygame_if_needed(self)
        render_environment(self, env)

        result = Render_Result()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                result.quit_requested = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                result.quit_requested = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                result.reset_requested = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                handle_entity_click(self, env, event.pos, button=event.button)
        return result
