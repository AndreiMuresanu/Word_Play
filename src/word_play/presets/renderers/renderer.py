from __future__ import annotations

import argparse
import os
import time
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from word_play.core import Component

from .draw import render_environment
from .layout import Grid_Layout_Adapter
from .runtime import configure_renderer, handle_entity_click, init_pygame_if_needed

if TYPE_CHECKING:
    from word_play.core import Environment

    from .layout import Position_Layout_Adapter


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
        last_message: str | None = None,
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
        self.last_message = last_message
        self._last_message_step: int | None = None


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
        width: int = 10,
        height: int = 10,
        default_floor_sprite: str = "sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png",
    ):
        """Configure renderer state, layout mapping, and sizing defaults."""
        configure_renderer(
            self,
            layout=layout,
            tile_size=tile_size,
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
        env.renderer_impl = self
        init_pygame_if_needed(self)
        render_environment(self, env)


_default_renderer: Pygame_Renderer | None = None


def render_step(
    env,
    *,
    renderer: Pygame_Renderer | None = None,
    step_delay: float = 0.0,
) -> bool:
    """Render one pygame frame and return False when the window should close."""
    global _default_renderer

    rend = renderer or _default_renderer
    if rend is None:
        rend = Pygame_Renderer(layout=Grid_Layout_Adapter(), tile_size=56)
        _default_renderer = rend

    init_pygame_if_needed(rend)
    env.renderer_impl = rend
    render_environment(rend, env)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            if rend is _default_renderer:
                _default_renderer = None
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            pygame.quit()
            if rend is _default_renderer:
                _default_renderer = None
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r and hasattr(env, "reset"):
            env.reset()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            handle_entity_click(rend, env, event.pos, button=event.button)

    if step_delay > 0:
        time.sleep(step_delay)

    return True


def _record_transient_frame(env: "Environment") -> None:
    recorder = getattr(env, "renderer_recorder", None)
    if recorder is None or getattr(env, "_recording_renderer_message_frame", False):
        return

    env._recording_renderer_message_frame = True
    try:
        recorder.record(env)
    finally:
        env._recording_renderer_message_frame = False


def _render_transient_frame(env: "Environment") -> None:
    renderer = getattr(env, "renderer_impl", None)
    if renderer is None:
        return

    init_pygame_if_needed(renderer)
    render_environment(renderer, env)


def record_render_message(
    entity: Any,
    message: str | None,
    env: "Environment" | None = None,
    *,
    record_frame: bool = True,
    render_frame: bool = True,
) -> None:
    if entity is None or message is None:
        return

    renderable = entity.get_component(Renderable)
    if renderable is None:
        return

    renderable.last_message = str(message)
    renderable._last_message_step = getattr(env, "cur_step", None) if env is not None else None
    if env is not None and record_frame:
        _record_transient_frame(env)
    if env is not None and render_frame:
        _render_transient_frame(env)


from .replay_and_live import (
    default_replay_renderer,
    newest_replay_log_path,
    replay,
    ReplayFrameEnvironment,
    replay_frames,
    replay_log_path,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Replay a recorded Word Play renderer log.")
    parser.add_argument(
        "log",
        nargs="?",
        default="simple_env_1",
        help="Experiment name, like simple_env_1, or a direct .pkl path.",
    )
    parser.add_argument("--autoplay", action="store_true", help="Start replay playback immediately.")
    parser.add_argument("--step-delay", type=float, default=0.28, help="Seconds between autoplay frames.")
    parser.add_argument("--print-path", action="store_true", help="Print the resolved replay log path and exit.")
    args = parser.parse_args(argv)

    log_path = replay_log_path(args.log)
    if args.print_path:
        print(log_path)
        return

    replay(log_path, autoplay=args.autoplay, step_delay=args.step_delay)


if __name__ == "__main__":
    main()
