from __future__ import annotations

from typing import TYPE_CHECKING, Any

from word_play.core import Entity, Render_Context, Render_Extractor, Render_Scene, Renderer_State
from word_play.presets.systems.inventory import Inventory

from .renderable import Renderable
from .wall_geometry import normalize_background_item

if TYPE_CHECKING:
    from word_play.core import Environment

    from ..layout import Position_Layout_Adapter


def _frame_step(env: "Environment") -> int:
    return int(getattr(env, "cur_step", getattr(env, "tick", 0)))


def _speech_step_is_visible(current_step: int, visible_step: Any) -> bool:
    try:
        step_value = int(visible_step)
    except (TypeError, ValueError):
        return True
    return step_value in (current_step, current_step + 1)


def _is_in_any_inventory(item: Any, env: "Environment") -> bool:
    if "in_inventory" in getattr(item, "tags", []):
        return True
    for entity in env.state.entities:
        inventory = entity.get_component(Inventory)
        if inventory and item in inventory.inventory:
            return True
    return False


class Frame_Metadata_Extractor(Render_Extractor):
    def extract(
        self,
        env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        scene.metadata.update(render_state.frame)
        scene.metadata.setdefault("simulation.step", _frame_step(env))
        scene.metadata.setdefault("simulation.is_replay", False)
        scene.metadata.setdefault("ui.hud_visible", True)


class Visible_Renderables_Extractor(Render_Extractor):
    def extract(
        self,
        env: "Environment",
        _render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        renderables: list[tuple[int, Entity, Renderable]] = []
        extra_background: list[dict[str, Any]] = []
        for entity in env.state.entities:
            renderable = entity.get_component(Renderable)
            if renderable is None or not renderable.visible or _is_in_any_inventory(entity, env):
                continue
            if getattr(renderable, "is_background", False):
                pos = getattr(entity, "position", None)
                if pos is not None:
                    extra_background.append({"x": int(pos.x), "y": int(pos.y), "sprite": renderable.sprite_path})
                continue
            renderables.append((renderable.z_index, entity, renderable))
        renderables.sort(key=lambda item: item[0])
        scene.layers["world.renderables"] = renderables
        if extra_background:
            scene.layers.setdefault("world.background_tiles", []).extend(extra_background)


class Background_Tiles_Extractor(Render_Extractor):
    def __init__(self, layout: "Position_Layout_Adapter"):
        self.layout = layout

    def extract(
        self,
        env: "Environment",
        _render_state: Renderer_State,
        scene: Render_Scene,
        context: Render_Context,
    ) -> None:
        self.layout.prepare_env(env, context)
        positioned_entities: list[tuple[Any, float, float]] = []
        for _, entity, _ in scene.layers.get("world.renderables", []):
            x, y = self.layout.screen_position(entity, env, context)
            positioned_entities.append((entity, x, y))

        background = self.layout.background(env, positioned_entities, context)
        scene.layers["world.background_tiles"] = [normalize_background_item(item) for item in background]


class Speech_Bubble_Extractor(Render_Extractor):
    def extract(
        self,
        env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        current_step = int(scene.metadata.get("simulation.step", _frame_step(env)))
        bubbles: list[dict[str, Any]] = []
        for event in render_state.events:
            if event.kind != "speech":
                continue
            bubble = dict(event.payload)
            visible_step = bubble.get("step", bubble.get("_step"))
            if visible_step is not None and not _speech_step_is_visible(current_step, visible_step):
                continue
            if "_step" in bubble:
                try:
                    bubble_step = int(bubble["_step"])
                except (TypeError, ValueError):
                    bubble_step = current_step
                if current_step > bubble_step:
                    continue
            bubbles.append(bubble)
        scene.layers["ui.speech_bubbles"] = bubbles


class Hit_Effect_Extractor(Render_Extractor):
    def extract(
        self,
        _env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        scene.layers["effects.entity_hits"] = [dict(event.payload) for event in render_state.events if event.kind == "hit"]


class Trade_Session_Extractor(Render_Extractor):
    """Reads ``render_state.events`` of kind ``"trade_session"``, merging by
    participant pair so multiple rounds accumulate into one session."""

    def extract(
        self,
        _env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        # Merge events by participant pair
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for event in render_state.events:
            if event.kind != "trade_session":
                continue
            p = event.payload
            left = p.get("left_name", "")
            right = p.get("right_name", "")
            key = (left, right) if left < right else (right, left)
            if key not in merged:
                merged[key] = {
                    "left": p.get("left_name", "Trader"),
                    "right": p.get("right_name", "Trader"),
                    "left_name": p.get("left_name", "Trader"),
                    "right_name": p.get("right_name", "Trader"),
                    "left_offer": "",
                    "right_offer": "",
                    "left_currency": "",
                    "right_currency": "",
                    "messages": [],
                    "accepted": "",
                    "round": 0,
                }
            session = merged[key]
            if p.get("left_offer"):
                session["left_offer"] = p["left_offer"]
            if p.get("right_offer"):
                session["right_offer"] = p["right_offer"]
            session["left_currency"] = p.get("left_currency", "") or session["left_currency"]
            session["right_currency"] = p.get("right_currency", "") or session["right_currency"]
            # Each event carries the full running transcript, so replace rather
            # than extend (extending would duplicate every prior line each round).
            event_messages = p.get("messages")
            if event_messages:
                session["messages"] = list(event_messages)
            session["round"] = max(session["round"], p.get("round", 0))
            if p.get("accepted"):
                session["accepted"] = p["accepted"]
        if merged:
            scene.layers["ui.trade_sessions"] = list(merged.values())


class Chat_Session_Extractor(Render_Extractor):
    """Reads ``render_state.events`` of kind ``"speech"`` with ``turn`` >= 0
    and groups them into ``ui.chat_sessions`` per set of participants."""

    def extract(
        self,
        _env: "Environment",
        render_state: Renderer_State,
        scene: Render_Scene,
        _context: Render_Context,
    ) -> None:
        # Collect speech events with conversation context
        conv: dict[frozenset[str], list[dict]] = {}
        names_by_key: dict[frozenset[str], list[str]] = {}
        for event in render_state.events:
            if event.kind != "speech":
                continue
            entity = event.payload.get("entity")
            if entity is None:
                continue
            sender_name = getattr(entity, "name", str(entity))
            text = str(event.payload.get("text", ""))
            turn = event.payload.get("turn", -1)
            if turn < 0:
                continue
            participant_names = event.payload.get("participant_names")
            if isinstance(participant_names, list) and participant_names:
                ordered_names = [str(name) for name in participant_names]
                key = frozenset(ordered_names)
            else:
                ordered_names = [sender_name]
                key = frozenset([sender_name])
            names_by_key.setdefault(key, ordered_names)
            session_messages = event.payload.get("session_messages")
            if isinstance(session_messages, list) and session_messages:
                conv[key] = [dict(message) for message in session_messages if isinstance(message, dict)]
            else:
                conv.setdefault(key, []).append({"sender": sender_name, "text": text, "turn": turn})

        sessions: list[dict[str, Any]] = []
        for key, msgs in conv.items():
            names = names_by_key.get(key, list(key))
            sessions.append({
                "participant_names": names,
                "messages": msgs,
            })
        if sessions:
            scene.layers["ui.chat_sessions"] = sessions


def default_pygame_extractors(layout: "Position_Layout_Adapter") -> list[Render_Extractor]:
    return [
        Frame_Metadata_Extractor(),
        Visible_Renderables_Extractor(),
        Background_Tiles_Extractor(layout),
        Speech_Bubble_Extractor(),
        Hit_Effect_Extractor(),
        Trade_Session_Extractor(),
        Chat_Session_Extractor(),
    ]
