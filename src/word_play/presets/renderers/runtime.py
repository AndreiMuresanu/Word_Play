from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

if TYPE_CHECKING:
    from .renderer import PygameRenderer, PositionLayoutAdapter


def configure_renderer(
    renderer: "PygameRenderer",
    *,
    layout: "PositionLayoutAdapter",
    tile_size: int,
    draw_grid_overlay: bool = False,
) -> None:
    renderer.layout = layout
    renderer.tile_size = tile_size
    renderer.hud_height = max(156, tile_size * 4)
    renderer.margin = max(12, tile_size // 2)
    renderer.default_draw_grid_overlay = draw_grid_overlay
    renderer.last_record_path = None
    renderer._pygame_initialized = False
    renderer._image_cache = {}
    renderer._scaled_image_cache = {}
    renderer._wall_set_cache = {}
    renderer._window_size = None
    renderer._last_health_values = {}
    renderer._damage_flash_until = {}


def init_pygame_if_needed(renderer: "PygameRenderer") -> None:
    if renderer._pygame_initialized:
        return

    if pygame is None:
        raise ImportError("pygame is required for PygameRenderer. Run `pip install pygame`")

    pygame.init()
    pygame.font.init()
    renderer.screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Environment Render")
    renderer.font = pygame.font.SysFont(None, renderer.tile_size)
    renderer.small_font = pygame.font.SysFont(None, max(16, renderer.tile_size // 2))
    renderer.hud_font = pygame.font.SysFont(None, max(20, renderer.tile_size // 2 + 6))
    renderer.speech_fonts = [
        pygame.font.SysFont(None, max(13, renderer.tile_size // 3)),
        pygame.font.SysFont(None, max(11, renderer.tile_size // 4)),
        pygame.font.SysFont(None, 10),
    ]
    renderer._pygame_initialized = True


def ensure_screen_size(renderer: "PygameRenderer", width: int, height: int) -> None:
    desired_size = (width, height)
    if renderer._window_size == desired_size:
        return
    renderer.screen = pygame.display.set_mode(desired_size)
    renderer._window_size = desired_size
