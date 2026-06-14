from __future__ import annotations

import pickle
import re
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from word_play.core import Action_Selection, Entity, Environment, Observation
from word_play.presets.systems.inventory import Inventory

from .renderable import Renderable


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


def is_in_any_inventory(item: Any, env: Environment) -> bool:
    """Check if an item is currently held by any entity."""
    if "in_inventory" in getattr(item, "tags", []):
        return True
    for entity in env.state.entities:
        inventory = entity.get_component(Inventory)
        if inventory and item in inventory.inventory:
            return True
    return False


def _json_safe(
    value: Any,
    entity_to_index: dict[Entity, int] | None = None,
    _seen: set | None = None,
) -> Any:
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if entity_to_index is not None and isinstance(value, Entity) and value in entity_to_index:
        return {"__entity_ref__": entity_to_index[value]}

    obj_id = id(value)
    if obj_id in _seen:
        return "<circular reference>"
    _seen.add(obj_id)

    try:
        if is_dataclass(value):
            return {
                field.name: _json_safe(getattr(value, field.name), entity_to_index, _seen)
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {str(key): _json_safe(item, entity_to_index, _seen) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item, entity_to_index, _seen) for item in value]
        if hasattr(value, "__dict__"):
            payload = {}
            for key, item in vars(value).items():
                if key == "entity":
                    continue
                payload[key] = _json_safe(item, entity_to_index, _seen)
            if payload:
                return payload
    finally:
        _seen.discard(obj_id)

    return str(value)


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
) -> dict[str, Any]:
    entity_to_index = {entity: index for index, entity in enumerate(env.state.entities)}
    entities = []
    for entity_index, entity in enumerate(env.state.entities):
        renderable = entity.get_component(Renderable)
        position = entity.position
        x = getattr(position, "x", None)
        y = getattr(position, "y", None)
        visible = False if renderable is None else renderable.visible and not is_in_any_inventory(entity, env)

        entities.append(
            {
                "entity_index": entity_index,
                "name": entity.name,
                "is_agent": entity.is_agent,
                "x": x,
                "y": y,
                "tags": list(entity.tags),
                "renderable": None
                if renderable is None
                else {
                    "sprite_path": renderable.sprite_path,
                    "z_index": renderable.z_index,
                    "visible": visible,
                    "overlay_sprite": getattr(renderable, "overlay_sprite", None),
                    "overlay_mode": getattr(renderable, "overlay_mode", "badge"),
                    "overlay_scale": getattr(renderable, "overlay_scale", None),
                    "wall_set": getattr(renderable, "wall_set", None),
                },
                "components": {
                    component_type.__name__: _json_safe(component, entity_to_index)
                    for component_type, component in entity.components.items()
                },
            }
        )

    agent_observations = []
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        agent_observations.append(
            {
                "agent_name": agent.name,
                **serialize_observation(observation),
            }
        )

    cur_step = getattr(env, "cur_step", 0)
    renderer_state = env.render_state

    return {
        "cur_step": cur_step,
        "tick": cur_step,
        "selected_actions": []
        if selected_actions is None
        else [serialize_action_selection(action_selection) for action_selection in selected_actions],
        "render_state_frame": _json_safe(dict(renderer_state.frame), entity_to_index),
        "render_state_events": _json_safe(list(renderer_state.events), entity_to_index),
        "entities": entities,
        "agent_observations": agent_observations,
    }


class ExperimentRecorder:
    def __init__(self, output_path: str | Path, title: str, metadata: dict[str, Any] | None = None):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.title = title
        self.metadata = metadata or {}
        self.frames: list[dict[str, Any]] = []
        self.newest_output_path = newest_experiment_log_path(title, root_dir=self.output_path.parent)

    def record(
        self,
        env: Environment,
        selected_actions: list[Action_Selection] | None = None,
    ) -> dict[str, Any]:
        frame = capture_environment_frame(
            env,
            selected_actions=selected_actions,
        )
        frame_index = len(self.frames)
        frame["frame_index"] = frame_index
        self.frames.append(frame)
        self.flush()
        return frame

    def payload(self) -> dict[str, Any]:
        return {
            "version": 4,
            "title": self.title,
            "metadata": self.metadata,
            "frame_count": len(self.frames),
            "frames": self.frames,
        }

    def flush(self) -> None:
        payload_bytes = pickle.dumps(self.payload())
        self.output_path.write_bytes(payload_bytes)
        self.newest_output_path.write_bytes(payload_bytes)


_default_recorder: ExperimentRecorder | None = None


def record_step(
    env: Environment,
    *,
    recorder: ExperimentRecorder | None = None,
    output_path: str | Path | None = None,
    title: str = "wordplay_experiment",
    metadata: dict[str, Any] | None = None,
    selected_actions: list[Action_Selection] | None = None,
) -> dict[str, Any]:
    """Record one replay frame."""
    global _default_recorder

    active_recorder = recorder or _default_recorder
    if active_recorder is None:
        active_recorder = ExperimentRecorder(
            output_path or default_experiment_log_path(title),
            title,
            metadata=metadata,
        )
        _default_recorder = active_recorder

    return active_recorder.record(env, selected_actions=selected_actions)


def load_recording_payload(log_path: str | Path) -> dict[str, Any]:
    """Load a pickled replay payload."""
    payload = pickle.loads(Path(log_path).read_bytes())
    if not isinstance(payload, dict):
        raise TypeError("Replay payload must be a dictionary.")
    return payload
