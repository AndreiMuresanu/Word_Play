from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from word_play.core import Component, Entity

if TYPE_CHECKING:
    from word_play.core import Environment
    from word_play.core.components import Agent_Policy

    from .layout import Position_Layout_Adapter


@dataclass
class LLMConfig:
    """Configuration for LLM mode."""
    model_name: str = "openai/gpt-4o"
    model_key: str = "default_model"
    base_url: str = "https://openrouter.ai/api/v1"
    policy_builder: Any = None
    sidebar_width: int | None = None


class Renderable(Component):
    """Store sprite and overlay metadata for an entity."""
    def __init__(
        self,
        sprite_path: str,
        z_index: int = 0,
        visible: bool = True,
        overlay_sprite: str | None = None,
        overlay_mode: str = "badge",
        overlay_scale: float | None = None,
        foreground_sprite: str | None = None,
        foreground_scale: float | None = None,
        shadow_scale: float = 0.72,
        bob_amplitude: float = 0.0,
        bob_speed: float = 1.6,
        animation_frames: list[str] | None = None,
        animation_fps: float = 5.0,
        emissive_sprite: str | None = None,
        emissive_intensity: int = 84,
        last_message: str | None = None,
        speech_bubble_scale: float = 1.0,  # Scale factor for speech bubbles (0.5 = half size)
    wall_set: str | None = None,
    ):
        super().__init__()
        self.sprite_path = sprite_path
        self.wall_set = wall_set
        self.z_index = z_index
        self.visible = visible
        self.overlay_sprite = overlay_sprite
        self.overlay_mode = overlay_mode
        self.overlay_scale = overlay_scale
        self.foreground_sprite = foreground_sprite
        self.foreground_scale = foreground_scale
        self.shadow_scale = shadow_scale
        self.bob_amplitude = bob_amplitude
        self.bob_speed = bob_speed
        self.animation_frames = list(animation_frames or [])
        self.animation_fps = animation_fps
        self.emissive_sprite = emissive_sprite
        self.emissive_intensity = emissive_intensity
        self.last_message = last_message
        self.speech_bubble_scale = speech_bubble_scale


class Renderer(ABC):
    @abstractmethod
    def render(self, env: "Environment") -> Any:
        """Render one environment frame using a concrete backend."""


class Pygame_Renderer(Renderer):
    """Concrete renderer that delegates drawing to pygame helpers."""
    def __init__(
        self,
        layout: "Position_Layout_Adapter",
        tile_size: int = 32,
        draw_grid_overlay: bool = False,
        width: int = 10,
        height: int = 10,
        default_floor_sprite: str = "sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png",
    ):
        """Configure renderer state, layout mapping, and sizing defaults."""
        from .runtime import configure_renderer
        configure_renderer(
            self,
            layout=layout,
            tile_size=tile_size,
            draw_grid_overlay=draw_grid_overlay,
        )
        self.width = width
        self.height = height
        self.default_floor_sprite = default_floor_sprite

    def background_tiles(self) -> list[dict]:
        """Return floor tiles for the grid.

        Returns a list of tile dicts with keys: x, y, z, sprite.
        Override default_floor_sprite in __init__ to change the tile sprite.
        """
        tiles = []
        for x in range(self.width):
            for y in range(self.height):
                tiles.append({
                    "x": x,
                    "y": y,
                    "z": 0,
                    "sprite": self.default_floor_sprite,
                })
        return tiles

    def render(self, env: "Environment") -> None:
        """Initialize pygame if needed and draw the current environment."""
        from .runtime import init_pygame_if_needed
        from .draw import render_environment
        init_pygame_if_needed(self)
        render_environment(self, env)
