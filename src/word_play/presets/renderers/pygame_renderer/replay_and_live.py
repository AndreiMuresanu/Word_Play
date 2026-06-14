from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from word_play.core import Entity, Render_Event, Renderer_State
from word_play.core.components import Component
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.systems.inventory import Inventory

from ..layout import Grid_Layout_Adapter
from .interactive_env import load_recording_payload
from .renderable import Renderable

if TYPE_CHECKING:
    from .renderer import Pygame_Renderer


def _decode_render_payload(value: Any, entities: list[Entity]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"__entity_ref__"}:
            try:
                return entities[int(value["__entity_ref__"])]
            except (IndexError, TypeError, ValueError):
                return None
        return {key: _decode_render_payload(item, entities) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_render_payload(item, entities) for item in value]
    return value


def _decode_render_events(events: list[Any], entities: list[Entity]) -> list[Render_Event]:
    decoded: list[Render_Event] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        payload = event.get("payload")
        if not isinstance(kind, str) or not isinstance(payload, dict):
            continue
        decoded.append(
            Render_Event(
                kind=kind,
                payload=_decode_render_payload(payload, entities),
            )
        )
    return decoded


def _legacy_render_events(frame: dict[str, Any], entities: list[Entity]) -> list[Render_Event]:
    renderer_lists = _decode_render_payload(dict(frame.get("renderer_state_lists") or {}), entities)
    legacy_events: list[Render_Event] = []
    for bubble in renderer_lists.get("ui.speech_bubbles", []):
        if isinstance(bubble, dict):
            legacy_events.append(Render_Event(kind="speech", payload=dict(bubble)))
    for hit in renderer_lists.get("effects.entity_hits", []):
        if isinstance(hit, dict):
            legacy_events.append(Render_Event(kind="hit", payload=dict(hit)))
    return legacy_events


class ReplayFrameEnvironment:
    """Minimal environment wrapper around one serialized replay frame."""

    def __init__(self, frame: dict[str, Any]):
        self.cur_step = frame.get("cur_step")
        if self.cur_step is None:
            self.cur_step = frame.get("frame_index", frame.get("tick", 0))
        self.tick = self.cur_step
        entities = self._build_entities(frame.get("entities", []))
        render_frame = _decode_render_payload(
            dict(frame.get("render_state_frame") or frame.get("renderer_state_values") or {}),
            entities,
        )
        render_events = _decode_render_events(list(frame.get("render_state_events") or []), entities)
        if not render_events:
            render_events = _legacy_render_events(frame, entities)
        renderer_state = Renderer_State(
            frame=render_frame,
            events=render_events,
        )
        self.state = SimpleNamespace(
            entities=entities,
            renderer_state=renderer_state,
        )
        self.agents = [entity for entity in self.state.entities if getattr(entity, "is_agent", False)]
        self.player = self.agents[0] if self.agents else None
        self.render_state.frame.setdefault("simulation.step", self.cur_step)
        self.render_state.frame["simulation.is_replay"] = True
        self._fill_sidebar_from_frame(frame)

    @property
    def render_state(self) -> Renderer_State:
        return self.state.renderer_state

    def _fill_sidebar_from_frame(self, frame: dict[str, Any]) -> None:
        if self.render_state.frame.get("ui.sidebar"):
            return

        selected_actions = list(frame.get("selected_actions", []))
        label = selected_actions[0]["label"] if selected_actions else "(no action chosen yet)"
        action_lines = ["Possible Actions:"]
        observations = list(frame.get("agent_observations", []))
        if observations:
            action_lines.extend(
                f"[{idx}] {item.get('label', '')}".rstrip()
                for idx, item in enumerate(observations[0].get("possible_actions", []))
            )
        if len(action_lines) == 1:
            action_lines.append("(no actions available)")

        self.render_state.frame["ui.sidebar"] = {
            "header": "Agent View",
            "selected_action": ["Chosen Action:", label],
            "actions": action_lines,
        }

    def _build_entities(self, entities: list[dict[str, Any]]) -> list[Entity]:
        built: list[Entity] = []
        for entity_data in entities:
            x = entity_data.get("x")
            y = entity_data.get("y")
            if x is None or y is None:
                continue

            components: list[Any] = []
            renderable_info = entity_data.get("renderable") or {}
            renderable = self._build_renderable(renderable_info)
            if renderable is not None:
                components.append(renderable)

            for component_name, component_payload in (entity_data.get("components") or {}).items():
                if component_name == "Renderable" or not isinstance(component_payload, dict):
                    continue
                component = self._build_component(str(component_name), component_payload)
                components.append(component)

            entity = Entity(
                name=entity_data["name"],
                position=Position_2D(int(x), int(y)),
                tags=list(entity_data.get("tags", [])),
                components=components,
            )
            entity.is_agent = bool(entity_data.get("is_agent", False))
            entity._replay_entity_index = int(entity_data.get("entity_index", len(built)))
            built.append(entity)

        return built

    def _build_renderable(self, renderable_info: dict[str, Any]) -> Renderable | None:
        sprite_path = renderable_info.get("sprite_path")
        if not sprite_path:
            return None

        return Renderable(
            sprite_path=sprite_path,
            z_index=renderable_info.get("z_index", 0),
            visible=renderable_info.get("visible", True),
            overlay_sprite=renderable_info.get("overlay_sprite"),
            overlay_mode=renderable_info.get("overlay_mode", "badge"),
            overlay_scale=renderable_info.get("overlay_scale"),
            wall_set=renderable_info.get("wall_set"),
        )

    def _build_component(self, component_name: str, component_payload: dict[str, Any]) -> Component:
        if component_name == "Inventory":
            return self._build_inventory(component_payload)

        component_type = type(component_name, (Component,), {})
        component = component_type()
        for field_name, field_value in component_payload.items():
            setattr(component, field_name, field_value)
        return component

    def _build_inventory(self, component_payload: dict[str, Any]) -> Inventory:
        inventory_size = component_payload.get("inventory_size", -1)
        if inventory_size is None:
            inventory_size = -1
        inventory = Inventory(
            collectable_tags=[],
            inventory_size=int(inventory_size),
            starting_inventory=[],
        )
        inventory.inventory = [
            self._build_inventory_item(item_payload)
            for item_payload in component_payload.get("inventory", [])
            if isinstance(item_payload, dict)
        ]
        return inventory

    def _build_inventory_item(self, entity_data: dict[str, Any]) -> Entity:
        position_payload = entity_data.get("position") or {}
        components = []
        renderable = self._build_renderable(self._inventory_item_renderable_info(entity_data))
        if renderable is not None:
            components.append(renderable)
        return Entity(
            name=str(entity_data.get("name", "Inventory Item")),
            position=Position_2D(int(position_payload.get("x", 0)), int(position_payload.get("y", 0))),
            tags=list(entity_data.get("tags", [])),
            components=components,
        )

    def _inventory_item_renderable_info(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        renderable_info = entity_data.get("renderable")
        if isinstance(renderable_info, dict):
            return renderable_info

        for component_name, component_payload in (entity_data.get("components") or {}).items():
            if "Renderable" in str(component_name) and isinstance(component_payload, dict):
                return component_payload
        return {}


def _remap_replay_entity(entity: Entity | None, replay_env: ReplayFrameEnvironment) -> Entity | None:
    if entity is None:
        return None
    target_index = getattr(entity, "_replay_entity_index", None)
    if target_index is None:
        return None
    for candidate in replay_env.state.entities:
        if getattr(candidate, "_replay_entity_index", None) == target_index:
            return candidate
    return None


def replay_frames(
    renderer: "Pygame_Renderer",
    frames: list[dict[str, Any]],
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Display serialized replay frames in pygame."""
    import pygame

    from .draw import render_environment
    from .runtime import handle_entity_click, init_pygame_if_needed, pygame_runtime

    init_pygame_if_needed(renderer)
    if not frames:
        raise ValueError("Replay log is empty.")

    clock = pygame.time.Clock()
    paused = not autoplay
    viewing_index = 0
    last_advance = time.monotonic()
    view = pygame_runtime(renderer).view
    view.camera_focus_entity = None
    view.selected_entity = None

    while True:
        replay_env = ReplayFrameEnvironment(dict(frames[viewing_index]))
        view.selected_entity = _remap_replay_entity(view.selected_entity, replay_env)
        view.camera_focus_entity = _remap_replay_entity(view.camera_focus_entity, replay_env)
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
    from .renderer import Pygame_Renderer

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
    from .renderer import Pygame_Renderer

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

    payload = load_recording_payload(resolved_log_path)
    replay_frames(
        renderer,
        payload.get("frames", []),
        autoplay=autoplay,
        step_delay=step_delay,
    )
