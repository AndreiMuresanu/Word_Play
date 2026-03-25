from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

from word_play.core import Component, Position

if TYPE_CHECKING:
    from pathlib import Path

    from word_play.core import Action_Selection, Environment


class Renderable(Component):
    def __init__(
        self,
        sprite_path: str,
        z_index: int = 0,
        visible: bool = True,
        overlay_sprite: str | None = None,
        overlay_mode: str = "badge",
        overlay_scale: float | None = None,
    ):
        super().__init__()
        self.sprite_path = sprite_path
        self.z_index = z_index
        self.visible = visible
        self.overlay_sprite = overlay_sprite
        self.overlay_mode = overlay_mode
        self.overlay_scale = overlay_scale


class Renderer(ABC):
    @abstractmethod
    def render(self, env: "Environment") -> Any:
        """Draw the given environment and return any renderer-specific output."""


class PositionLayoutAdapter(ABC):
    @abstractmethod
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert an environment position into screen/grid coordinates."""

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return optional background draw data for the environment."""
        return []


class GridLayoutAdapter(PositionLayoutAdapter):
    def screen_position(self, position: Position) -> tuple[float, float]:
        return float(position.x), float(position.y)


class EnvironmentLayoutAdapter(GridLayoutAdapter):
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        background_tiles = getattr(env, "background_tiles", None)
        return [] if background_tiles is None else background_tiles()


from .draw import render_environment
from .replay_and_live import replay_frames, replay_recording, run_live_view
from .runtime import configure_renderer, init_pygame_if_needed


class PygameRenderer(Renderer):
    def __init__(self, layout: PositionLayoutAdapter, tile_size: int = 32, draw_grid_overlay: bool = False):
        configure_renderer(self, layout=layout, tile_size=tile_size, draw_grid_overlay=draw_grid_overlay)

    def render(self, env: "Environment") -> None:
        init_pygame_if_needed(self)
        render_environment(self, env)

    def replay_frames(
        self,
        frames: list[dict[str, Any]],
        *,
        autoplay: bool = False,
        step_delay: float = 0.28,
    ) -> None:
        replay_frames(self, frames, autoplay=autoplay, step_delay=step_delay)

    def replay_recording(
        self,
        log_path: str | "Path",
        *,
        autoplay: bool = False,
        step_delay: float = 0.28,
    ) -> None:
        replay_recording(self, log_path, autoplay=autoplay, step_delay=step_delay)

    def run_live_view(
        self,
        env: "Environment",
        *,
        step_builder: Callable[["Environment"], list["Action_Selection"]],
        recorder: Any | None = None,
        keep_logs: bool = True,
        log_path: str | "Path" | None = None,
        log_root: str | "Path" | None = None,
        record_title: str = "Environment Replay",
        record_metadata: dict[str, Any] | None = None,
        autoplay: bool = True,
        step_delay: float = 0.28,
        max_steps: int | None = None,
        reset_factory: Callable[[], "Environment"] | None = None,
        initial_notes: list[str] | None = None,
        autofill_required_kwargs: Callable[["Action_Selection"], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        return run_live_view(
            self,
            env,
            step_builder=step_builder,
            recorder=recorder,
            keep_logs=keep_logs,
            log_path=log_path,
            log_root=log_root,
            record_title=record_title,
            record_metadata=record_metadata,
            autoplay=autoplay,
            step_delay=step_delay,
            max_steps=max_steps,
            reset_factory=reset_factory,
            initial_notes=initial_notes,
            autofill_required_kwargs=autofill_required_kwargs,
        )


def render(
    env: "Environment",
    *,
    renderer: PygameRenderer | None = None,
    tile_size: int = 32,
    draw_grid_overlay: bool = False,
) -> PygameRenderer:
    active_renderer = renderer or getattr(env, "renderer_impl", None)
    if active_renderer is None:
        active_renderer = PygameRenderer(
            layout=EnvironmentLayoutAdapter(),
            tile_size=tile_size,
            draw_grid_overlay=draw_grid_overlay,
        )
    active_renderer.render(env)
    return active_renderer


def replay(
    log_path: str | "Path",
    *,
    tile_size: int = 32,
    draw_grid_overlay: bool = False,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    renderer = PygameRenderer(
        layout=EnvironmentLayoutAdapter(),
        tile_size=tile_size,
        draw_grid_overlay=draw_grid_overlay,
    )
    renderer.replay_recording(log_path, autoplay=autoplay, step_delay=step_delay)
