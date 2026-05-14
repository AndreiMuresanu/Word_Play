from __future__ import annotations

import pickle
import re
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from word_play.core import Action_Selection, Environment, Observation

from .layout import Environment_Layout_Adapter
from .renderer import Renderable


def default_experiment_log_path(
    title: str,
    *,
    root_dir: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "experiment"
    base_dir = (
        Path(root_dir)
        if root_dir is not None
        else Path(__file__).resolve().parents[3] / "experiments" / "logs"
    )
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return base_dir / f"{slug}_{stamp}.pkl"


def newest_experiment_log_path(
    title: str,
    *,
    root_dir: str | Path | None = None,
) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "experiment"
    base_dir = (
        Path(root_dir)
        if root_dir is not None
        else Path(__file__).resolve().parents[3] / "experiments" / "logs"
    )
    return base_dir / f"{slug}_newest.pkl"


def _json_safe(value: Any, _seen: set | None = None) -> Any:
    if _seen is None:
        _seen = set()

    # Handle primitives
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Guard against circular references
    obj_id = id(value)
    if obj_id in _seen:
        return "<circular reference>"
    _seen.add(obj_id)

    try:
        if is_dataclass(value):
            return {key: _json_safe(item, _seen) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): _json_safe(item, _seen) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item, _seen) for item in value]
        if hasattr(value, "__dict__"):
            payload = {}
            for key, item in vars(value).items():
                if key == "entity":
                    continue
                payload[key] = _json_safe(item, _seen)
            if payload:
                return payload
            return str(value)
    finally:
        _seen.discard(obj_id)


def serialize_action_selection(action_selection: Action_Selection, index: int | None = None) -> dict[str, Any]:
    payload = {
        "label": str(action_selection),
        "actor_name": action_selection.actor.name,
        "target_name": action_selection.target_entity.name,
        "action_type": action_selection.action.__class__.__name__,
        "required_kwargs": {},
    }
    if index is not None:
        payload["index"] = index
    if action_selection.required_kwargs:
        payload["required_kwargs"] = {
            name: arg.arg_description(action_selection.actor, action_selection.target_entity, action_selection.env)
            for name, arg in action_selection.required_kwargs.items()
        }
    return payload


def serialize_observation(observation: Observation) -> dict[str, Any]:
    return {
        "text": str(observation),
        "possible_actions": [
            serialize_action_selection(action_selection, index=index)
            for index, action_selection in enumerate(observation.possible_actions)
        ],
    }


def capture_environment_frame(
    env: Environment,
    selected_actions: list[Action_Selection] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
    draw_grid_overlay: bool | None = None,
) -> dict[str, Any]:
    hit_entity_names = [
        str(effect.get("entity_name"))
        for effect in list(getattr(env, "hit_effects", []))
        if effect.get("entity_name")
    ]
    # Background tiles from env if available; otherwise auto-fill from width/height.
    _env_bg = getattr(env, "background_tiles", None)
    if callable(_env_bg):
        _env_bg = _env_bg()
    background_tiles = list(_env_bg) if _env_bg else []
    if not background_tiles:
        floor_sprite = getattr(env, "floor_sprite", None) or "src/world_tiles/indoors/floors/day_brick_floor_c.png"
        width = int(getattr(env, "width", 0) or 0)
        height = int(getattr(env, "height", 0) or 0)
        if width > 0 and height > 0:
            background_tiles = [
                {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                for x in range(width)
                for y in range(height)
            ]

    entities = []
    min_x = max_x = min_y = max_y = 0
    bounds_initialized = False
    for entity in env.state.entities:
        renderable = entity.get_component(Renderable)
        position = entity.position
        x = getattr(position, "x", None)
        y = getattr(position, "y", None)
        if x is not None and y is not None:
            if not bounds_initialized:
                min_x = max_x = int(x)
                min_y = max_y = int(y)
                bounds_initialized = True
            else:
                min_x = min(min_x, int(x))
                max_x = max(max_x, int(x))
                min_y = min(min_y, int(y))
                max_y = max(max_y, int(y))

        entities.append(
            {
                "name": entity.name,
                "is_agent": entity.is_agent,
                "position_label": str(position),
                "x": x,
                "y": y,
                "tags": list(entity.tags),
                "renderable": None
                if renderable is None
                else {
                    "sprite_path": renderable.sprite_path,
                    "z_index": renderable.z_index,
                    "visible": renderable.visible,
                    "overlay_sprite": getattr(renderable, "overlay_sprite", None),
                    "overlay_mode": getattr(renderable, "overlay_mode", "badge"),
                    "overlay_scale": getattr(renderable, "overlay_scale", None),
                    "foreground_sprite": getattr(renderable, "foreground_sprite", None),
                    "foreground_scale": getattr(renderable, "foreground_scale", None),
                    "shadow_scale": getattr(renderable, "shadow_scale", 0.72),
                    "bob_amplitude": getattr(renderable, "bob_amplitude", 0.0),
                    "bob_speed": getattr(renderable, "bob_speed", 1.6),
                    "animation_frames": list(getattr(renderable, "animation_frames", [])),
                    "animation_fps": getattr(renderable, "animation_fps", 5.0),
                    "emissive_sprite": getattr(renderable, "emissive_sprite", None),
                    "emissive_intensity": getattr(renderable, "emissive_intensity", 84),
                },
                "overlay": None if renderable is None else getattr(renderable, "overlay_sprite", None),
                "components": {
                    component_type.__name__: _json_safe(component)
                    for component_type, component in entity.components.items()
                },
            }
        )

    if background_tiles:
        for item in background_tiles:
            x = item.get("x")
            y = item.get("y")
            if x is None or y is None:
                continue
            if not bounds_initialized:
                min_x = max_x = int(x)
                min_y = max_y = int(y)
                bounds_initialized = True
            else:
                min_x = min(min_x, int(x))
                max_x = max(max_x, int(x))
                min_y = min(min_y, int(y))
                max_y = max(max_y, int(y))

    agent_observations = []
    available_actions = {}
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        agent_observations.append(
            {
                "agent_name": agent.name,
                **serialize_observation(observation),
            }
        )
        available_actions[agent.name] = [
            serialize_action_selection(action_selection, index=index)
            for index, action_selection in enumerate(env.possible_actions(agent))
        ]

    visible_tiles = None
    env_visible_tiles = getattr(env, "visible_tiles", None)
    if callable(env_visible_tiles):
        visible_tiles = [list(tile) for tile in env_visible_tiles()]

    return {
        "frame_type": frame_type,
        "tick": getattr(env, "tick", getattr(env, "cur_step", 0)),
        "description": env.description,
        "score": getattr(env, "score", None),
        "width": getattr(env, "width", None),
        "height": getattr(env, "height", None),
        "floor_sprite": getattr(env, "floor_sprite", None),
        "deliveries": getattr(env, "deliveries", None),
        "terminations": list(getattr(env, "terminations", [])),
        "truncations": list(getattr(env, "truncations", [])),
        "final_boss_defeated": bool(getattr(env, "final_boss_defeated", False)),
        "draw_grid_overlay": bool(getattr(env, "draw_grid_overlay", False) if draw_grid_overlay is None else draw_grid_overlay),
        "hud_header": getattr(env, "hud_header", None),
        "hud_lines": list(getattr(env, "hud_lines", [])),
        "hud_sidebar_header": getattr(env, "hud_sidebar_header", None),
        "hud_sidebar_lines": list(getattr(env, "hud_sidebar_lines", [])),
        "hud_sidebar_selected_action": list(getattr(env, "hud_sidebar_selected_action", [])),
        "hud_sidebar_actions": list(getattr(env, "hud_sidebar_actions", [])),
        "hud_sidebar_width": getattr(env, "hud_sidebar_width", None),
        "current_phase": getattr(env, "current_phase", None),
        "hide_bottom_hud": bool(getattr(env, "hide_bottom_hud", False)),
        "sight_radius": getattr(env, "sight_radius", None),
        "speech_bubble_sprite": getattr(env, "speech_bubble_sprite", None),
        "speech_bubbles": _json_safe(list(getattr(env, "speech_bubbles", []))),
        "event_log": list(getattr(env, "event_log", [])),
        "hit_entity_names": hit_entity_names,
        "hit_effects": _json_safe(list(getattr(env, "hit_effects", []))),
        "visible_tiles": visible_tiles,
        "notes": list(notes or []),
        "selected_actions": []
        if selected_actions is None
        else [serialize_action_selection(action_selection) for action_selection in selected_actions],
        "bounds": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
        },
        "background_tiles": background_tiles,
        "entities": entities,
        "agent_observations": agent_observations,
        "available_actions": available_actions,
    }


class ExperimentRecorder:
    def __init__(self, output_path: str | Path, title: str, metadata: dict[str, Any] | None = None):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.title = title
        self.metadata = metadata or {}
        self.frames: list[dict[str, Any]] = []
        self._env_states: list[Any] = []  # kept in-memory for pygame replay, not flushed
        self.newest_output_path = newest_experiment_log_path(title, root_dir=self.output_path.parent)

    def record(
        self,
        env: Environment,
        selected_actions: list[Action_Selection] | None = None,
        notes: list[str] | None = None,
        frame_type: str = "state",
        draw_grid_overlay: bool | None = None,
    ) -> dict[str, Any]:
        frame = capture_environment_frame(
            env,
            selected_actions=selected_actions,
            notes=notes,
            frame_type=frame_type,
            draw_grid_overlay=draw_grid_overlay,
        )
        self._env_states.append(deepcopy(env.state))
        frame["frame_index"] = len(self.frames)
        self.frames.append(frame)
        self.flush()
        return frame

    def get_env_state(self, frame_index: int) -> Any:
        return self._env_states[frame_index] if 0 <= frame_index < len(self._env_states) else None

    def payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "title": self.title,
            "metadata": self.metadata,
            "frame_count": len(self.frames),
            "frames": self.frames,
        }

    def flush(self) -> None:
        payload_bytes = pickle.dumps(self.payload())
        self.output_path.write_bytes(payload_bytes)
        self.newest_output_path.write_bytes(payload_bytes)


class InteractiveEnvironmentSession:
    def __init__(self, env: Environment, title: str, recorder: ExperimentRecorder | None = None):
        self.env = env
        self.title = title
        self.recorder = recorder
        self.history: list[dict[str, Any]] = []
        self._capture(frame_type="initial", notes=["Interactive session ready."])

    def _capture(
        self,
        selected_actions: list[Action_Selection] | None = None,
        notes: list[str] | None = None,
        frame_type: str = "state",
        draw_grid_overlay: bool | None = None,
    ) -> dict[str, Any]:
        frame = capture_environment_frame(
            self.env,
            selected_actions=selected_actions,
            notes=notes,
            frame_type=frame_type,
            draw_grid_overlay=draw_grid_overlay,
        )
        frame["frame_index"] = len(self.history)
        self.history.append(frame)
        if self.recorder is not None:
            self.recorder.record(
                self.env,
                selected_actions=selected_actions,
                notes=notes,
                frame_type=frame_type,
                draw_grid_overlay=draw_grid_overlay,
            )
        return frame

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": "interactive",
            "title": self.title,
            "history": self.history,
            "current_frame": self.history[-1],
            "agents": [
                {
                    "agent_name": agent.name,
                    "actions": [
                        serialize_action_selection(action_selection, index=index)
                        for index, action_selection in enumerate(self.env.possible_actions(agent))
                    ],
                }
                for agent in self.env.agents
            ],
        }

    def submit_step(self, action_requests: list[dict[str, Any]]) -> dict[str, Any]:
        requested_by_agent = {request["agent_name"]: request for request in action_requests}
        selections: list[Action_Selection] = []
        for agent in self.env.agents:
            if agent.name not in requested_by_agent:
                raise ValueError(f"Missing action for agent '{agent.name}'.")

            request = requested_by_agent[agent.name]
            possible_actions = self.env.possible_actions(agent)
            action_index = int(request["action_index"])
            if action_index < 0 or action_index >= len(possible_actions):
                raise ValueError(f"Invalid action index {action_index} for agent '{agent.name}'.")

            selection = possible_actions[action_index]
            kwargs_text = (request.get("kwargs_text") or "").strip()
            if selection.required_kwargs:
                selection.action_kwargs = selection.parse_and_validate_kwarg_list(kwargs_text)
            else:
                selection.action_kwargs = {}
            selections.append(selection)

        self.env.step(selections)
        self._capture(
            selected_actions=selections,
            notes=[f"{selection.actor.name}: {selection}" for selection in selections],
            frame_type="step",
        )
        return self.snapshot()


def load_recording_payload(log_path: str | Path) -> dict[str, Any]:
    """Load a pickled replay payload from disk."""
    return pickle.loads(Path(log_path).read_bytes())
