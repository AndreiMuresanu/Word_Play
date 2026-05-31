from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity
from word_play.core.components import Component
from word_play.presets.movement.simple_2d_grid import Position_2D

from .draw import render_environment
from .interactive_env import load_recording_payload
from .renderer import Renderable
from .runtime import init_pygame_if_needed

if TYPE_CHECKING:
    from .renderer import Pygame_Renderer


class ReplayFrameEnvironment:
    """Minimal environment wrapper around one serialized replay frame."""

    def __init__(self, frame: dict[str, Any]):
        self.tick = frame.get("tick", 0)
        self.score = frame.get("score", 0)
        self.hit_effects = list(frame.get("hit_effects", []))
        self.sight_radius = frame.get("sight_radius")
        self.current_phase = frame.get("current_phase")
        self.hide_bottom_hud = bool(frame.get("hide_bottom_hud", False))
        self.speech_bubbles = list(frame.get("speech_bubbles", []))

        self.hud_sidebar_header = frame.get("hud_sidebar_header")
        self.hud_sidebar_lines = list(frame.get("hud_sidebar_lines", []))
        self.hud_sidebar_selected_action = list(frame.get("hud_sidebar_selected_action", []))
        self.hud_sidebar_actions = list(frame.get("hud_sidebar_actions", []))
        self.hud_sidebar_width = frame.get("hud_sidebar_width")

        self._visible_tiles = [tuple(tile) for tile in frame.get("visible_tiles", [])]
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

    @property
    def visible_tiles(self) -> list[tuple[int, int]]:
        if self._visible_tiles:
            return list(self._visible_tiles)
        if self.player is None or not isinstance(self.sight_radius, int):
            return []

        player_position = getattr(self.player, "position", None)
        if player_position is None:
            return []

        xs = [int(item["x"]) for item in self._background_tiles if item.get("x") is not None]
        ys = [int(item["y"]) for item in self._background_tiles if item.get("y") is not None]
        xs.extend(getattr(entity.position, "x", 0) for entity in self.state.entities)
        ys.extend(getattr(entity.position, "y", 0) for entity in self.state.entities)
        if not xs or not ys:
            return []

        return [
            (x, y)
            for y in range(min(ys), max(ys) + 1)
            for x in range(min(xs), max(xs) + 1)
            if max(abs(player_position.x - x), abs(player_position.y - y)) <= self.sight_radius
        ]


def handle_entity_click(renderer: "Pygame_Renderer", env: ReplayFrameEnvironment, mouse_pos: tuple[int, int]) -> None:
    """Select clicked entities during replay and focus clicked agents."""
    for entity in env.state.entities:
        rect = renderer._last_drawn_entity_rects.get(entity.name)
        if rect is None or not rect.collidepoint(mouse_pos):
            continue

        renderer.selected_entity_name = entity.name
        renderer.camera_focus_entity_name = entity.name if entity.is_agent else None
        if renderer.camera_focus_entity_name is not None and isinstance(env.sight_radius, int):
            renderer.camera_focus_radius_tiles = max(2, env.sight_radius)
        if renderer.camera_focus_entity_name is None:
            renderer.camera_center = None
        return

    renderer.selected_entity_name = None
    renderer.camera_focus_entity_name = None
    renderer.camera_center = None


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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handle_entity_click(renderer, replay_env, event.pos)
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

        if not paused and time.monotonic() - last_advance >= step_delay:
            if viewing_index >= len(frames) - 1:
                paused = True
            else:
                viewing_index += 1
                last_advance = time.monotonic()

        clock.tick(60)


def replay(
    renderer: "Pygame_Renderer",
    log_path: str | Path,
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Load a recording file and replay it."""
    payload = load_recording_payload(log_path)
    replay_frames(
        renderer,
        payload.get("frames", []),
        autoplay=autoplay,
        step_delay=step_delay,
    )
