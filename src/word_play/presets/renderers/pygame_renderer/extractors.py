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
        for entity in env.state.entities:
            renderable = entity.get_component(Renderable)
            if renderable is None or not renderable.visible or _is_in_any_inventory(entity, env):
                continue
            renderables.append((renderable.z_index, entity, renderable))
        renderables.sort(key=lambda item: item[0])
        scene.layers["world.renderables"] = renderables


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


def default_pygame_extractors(layout: "Position_Layout_Adapter") -> list[Render_Extractor]:
    return [
        Frame_Metadata_Extractor(),
        Visible_Renderables_Extractor(),
        Background_Tiles_Extractor(layout),
        Speech_Bubble_Extractor(),
        Hit_Effect_Extractor(),
    ]
