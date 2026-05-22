from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import Pygame_Renderer


def focus_radius(env: "Environment", renderer: "Pygame_Renderer") -> int:
    """Resolve the active focus radius from the environment observation settings."""
    for attr in ("observation_radius", "sight_radius"):
        radius = getattr(env, attr, None)
        if isinstance(radius, int) and radius >= 0:
            return radius
    return max(0, int(getattr(renderer, "camera_focus_radius_tiles", 6)))


def set_focus_from_click(renderer: "Pygame_Renderer", env: "Environment", mouse_pos: tuple[int, int]) -> None:
    """Select clicked entities and follow clicked agents; clear focus on empty space."""
    for entity in getattr(env.state, "entities", []):
        rect = renderer._last_drawn_entity_rects.get(entity.name)
        if rect is None or not rect.collidepoint(mouse_pos):
            continue
        renderer.selected_entity_name = entity.name
        renderer.camera_focus_entity_name = entity.name if getattr(entity, "is_agent", False) else None
        if renderer.camera_focus_entity_name is not None:
            renderer.camera_focus_radius_tiles = focus_radius(env, renderer)
        else:
            renderer.camera_center = None
        return

    renderer.selected_entity_name = None
    renderer.camera_focus_entity_name = None
    renderer.camera_center = None
