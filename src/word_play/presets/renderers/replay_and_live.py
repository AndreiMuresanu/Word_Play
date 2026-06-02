from __future__ import annotations

import pickle
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pygame

from word_play.core import Entity
from word_play.core.components import Component
from word_play.presets.movement.simple_2d_grid import Position_2D

from .draw import render_environment
from .layout import Grid_Layout_Adapter
from .runtime import handle_entity_click, init_pygame_if_needed


class ReplayFrameEnvironment:
    """Minimal environment wrapper around one serialized replay frame."""

    def __init__(self, frame: dict[str, Any]):
        self.cur_step = frame.get("cur_step")
        if self.cur_step is None:
            self.cur_step = frame.get("frame_index", frame.get("tick", 0))
        self.tick = self.cur_step
        self.is_replay = True
        self.score = frame.get("score", 0)
        self.hit_effects = list(frame.get("hit_effects", []))
        self.observation_radius = frame.get("observation_radius")
        self.current_phase = frame.get("current_phase")
        self.hide_bottom_hud = bool(frame.get("hide_bottom_hud", False))
        self.speech_bubbles = list(frame.get("speech_bubbles", []))

        self.hud_sidebar_header = frame.get("hud_sidebar_header")
        self.hud_sidebar_lines = list(frame.get("hud_sidebar_lines", []))
        self.hud_sidebar_selected_action = list(frame.get("hud_sidebar_selected_action", []))
        self.hud_sidebar_actions = list(frame.get("hud_sidebar_actions", []))
        self.hud_sidebar_compact_observation = bool(frame.get("hud_sidebar_compact_observation", False))
        self.hud_sidebar_width = frame.get("hud_sidebar_width")

        self._background_tiles = list(frame.get("background_tiles", []))
        self.state = SimpleNamespace(entities=self._build_entities(frame.get("entities", [])))
        self.agents = [entity for entity in self.state.entities if getattr(entity, "is_agent", False)]
        self.player = self.agents[0] if self.agents else None
        self._fill_sidebar_from_frame(frame)

    def _fill_sidebar_from_frame(self, frame: dict[str, Any]) -> None:
        if not self.hud_sidebar_selected_action:
            selected_actions = list(frame.get("selected_actions", []))
            label = selected_actions[0]["label"] if selected_actions else "(no action chosen yet)"
            self.hud_sidebar_selected_action = ["Chosen Action:", label]

        if self.hud_sidebar_actions:
            return

        action_lines = ["Possible Actions:"]
        observations = list(frame.get("agent_observations", []))
        if observations:
            action_lines.extend(
                f"[{idx}] {item.get('label', '')}".rstrip()
                for idx, item in enumerate(observations[0].get("possible_actions", []))
            )
        if len(action_lines) == 1:
            action_lines.append("(no actions available)")
        self.hud_sidebar_actions = action_lines

    def _build_entities(self, entities: list[dict[str, Any]]) -> list[Entity]:
        built: list[Entity] = []
        for entity_data in entities:
            x = entity_data.get("x")
            y = entity_data.get("y")
            if x is None or y is None:
                continue

            components: list[Any] = []
            renderable_info = entity_data.get("renderable") or {}
            sprite_path = renderable_info.get("sprite_path")
            if sprite_path:
                components.append(
                    Renderable(
                        sprite_path=sprite_path,
                        z_index=renderable_info.get("z_index", 0),
                        visible=renderable_info.get("visible", True),
                        overlay_sprite=renderable_info.get("overlay_sprite"),
                        overlay_mode=renderable_info.get("overlay_mode", "badge"),
                        overlay_scale=renderable_info.get("overlay_scale"),
                        last_message=renderable_info.get("last_message"),
                        wall_set=renderable_info.get("wall_set"),
                    )
                )

            for component_name, component_payload in (entity_data.get("components") or {}).items():
                if component_name == "Renderable" or not isinstance(component_payload, dict):
                    continue
                component_type = type(str(component_name), (Component,), {})
                component = component_type()
                for field_name, field_value in component_payload.items():
                    setattr(component, field_name, field_value)
                components.append(component)

            entity = Entity(
                name=entity_data["name"],
                position=Position_2D(int(x), int(y)),
                tags=list(entity_data.get("tags", [])),
                components=components,
            )
            entity.is_agent = bool(entity_data.get("is_agent", False))
            built.append(entity)

        return built

    @property
    def background_tiles(self) -> list[dict[str, Any]]:
        return list(self._background_tiles)

def replay_frames(
    renderer: "Pygame_Renderer",
    frames: list[dict[str, Any]],
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Display serialized replay frames in pygame."""
    init_pygame_if_needed(renderer)
    if not frames:
        raise ValueError("Replay log is empty.")

    clock = pygame.time.Clock()
    paused = not autoplay
    viewing_index = 0
    last_advance = time.monotonic()
    renderer.camera_focus_entity_name = None

    while True:
        replay_env = ReplayFrameEnvironment(dict(frames[viewing_index]))
        render_environment(renderer, replay_env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                handle_entity_click(renderer, replay_env, event.pos, button=event.button)
                continue
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                return
            if event.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
                paused = True
                viewing_index = min(len(frames) - 1, viewing_index + 1)
            elif event.key == pygame.K_LEFT:
                paused = True
                viewing_index = max(0, viewing_index - 1)
            elif event.key == pygame.K_r:
                viewing_index = 0
                paused = True
            elif event.key == pygame.K_HOME:
                paused = True
                viewing_index = 0
            elif event.key == pygame.K_END:
                paused = True
                viewing_index = len(frames) - 1
            elif event.key == pygame.K_SPACE:
                paused = not paused
                last_advance = time.monotonic()

        if not paused and time.monotonic() - last_advance >= step_delay:
            if viewing_index >= len(frames) - 1:
                paused = True
            else:
                viewing_index += 1
                last_advance = time.monotonic()

        clock.tick(60)


def default_replay_renderer() -> Pygame_Renderer:
    return Pygame_Renderer(Grid_Layout_Adapter(), tile_size=56)


def newest_replay_log_path(title: str, root_dir: str | Path | None = None) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "experiment"
    base_dir = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[3] / "experiments" / "logs"
    return base_dir / f"{slug}_newest.pkl"


def replay_log_path(log_or_title: str | Path) -> Path:
    path = Path(log_or_title)
    if path.suffix == ".pkl" or path.exists():
        return path
    return newest_replay_log_path(str(log_or_title))


def replay(
    log_path: str | Path | Pygame_Renderer,
    renderer_or_log_path: Pygame_Renderer | str | Path | None = None,
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Load a recording file and replay it."""
    if isinstance(log_path, Pygame_Renderer):
        if renderer_or_log_path is None or isinstance(renderer_or_log_path, Pygame_Renderer):
            raise TypeError("Use replay(log_path) or replay(renderer, log_path).")
        renderer = log_path
        resolved_log_path = renderer_or_log_path
    else:
        resolved_log_path = replay_log_path(log_path)
        if renderer_or_log_path is not None and not isinstance(renderer_or_log_path, Pygame_Renderer):
            raise TypeError("Use replay(log_path) or replay(log_path, renderer).")
        renderer = renderer_or_log_path or default_replay_renderer()

    payload = pickle.loads(Path(resolved_log_path).read_bytes())
    replay_frames(
        renderer,
        payload.get("frames", []),
        autoplay=autoplay,
        step_delay=step_delay,
    )


from .renderer import Pygame_Renderer, Renderable
