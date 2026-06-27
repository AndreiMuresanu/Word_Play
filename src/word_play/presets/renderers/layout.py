from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Environment, Render_Context


_DEFAULT_FLOOR = "src/world_tiles/indoors/floors/day_brick_floor_c.png"



def _render_frame(env: "Environment" | None) -> dict[str, Any]:
    if env is None:
        return {}
    render_state = getattr(env, "render_state", None)
    if render_state is None:
        return {}
    return getattr(render_state, "frame", {})


def _entity_grid_position(entity: Any) -> tuple[int, int] | None:
    position = getattr(entity, "position", None)
    x = getattr(position, "x", None)
    y = getattr(position, "y", None)
    if x is None or y is None:
        return None
    return int(x), int(y)


def inferred_floor_tiles(
    positioned_entities: list[tuple[Any, float, float]],
    floor_sprite: str,
) -> list[dict[str, Any]]:
    positions = [(int(x), int(y)) for _, x, y in positioned_entities]
    if not positions:
        return []

    xs = [position[0] for position in positions]
    ys = [position[1] for position in positions]
    return [
        {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
        for x in range(min(xs), max(xs) + 1)
        for y in range(min(ys), max(ys) + 1)
    ]


def _floor_tiles_from_bounds(bounds: Any, floor_sprite: str) -> list[dict[str, Any]]:
    if isinstance(bounds, dict):
        min_x = int(bounds.get("min_x", 0))
        max_x = int(bounds.get("max_x", min_x))
        min_y = int(bounds.get("min_y", 0))
        max_y = int(bounds.get("max_y", min_y))
    elif isinstance(bounds, (tuple, list)) and len(bounds) == 4:
        min_x, max_x, min_y, max_y = (int(value) for value in bounds)
    else:
        return []

    return [
        {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
        for x in range(min_x, max_x + 1)
        for y in range(min_y, max_y + 1)
    ]


class Position_Layout_Adapter(ABC):
    """Map environment positions and optional backgrounds into render space."""

    @abstractmethod
    def screen_position(
        self,
        entity: Any,
        env: "Environment",
        context: "Render_Context | None" = None,
    ) -> tuple[float, float]:
        """Convert a world position into renderer grid coordinates."""

    def background(
        self,
        env: "Environment",
        positioned_entities: list[tuple[Any, float, float]],
        _context: "Render_Context | None" = None,
    ) -> list[dict[str, Any]]:
        """Return background tiles to draw behind entities."""
        return []

    def prepare_env(self, env: "Environment", _context: "Render_Context | None" = None) -> None:
        """Update any renderer-facing derived state before drawing."""
        return None

    def should_render(self, entity: Any) -> bool:
        """Whether an entity should be drawn. Layouts may restrict this
        (e.g. the single-point layout renders only agent entities)."""
        return True


class Grid_Layout_Adapter(Position_Layout_Adapter):
    """Use entity x/y values directly as grid coordinates."""

    def background(
        self,
        env: "Environment",
        positioned_entities: list[tuple[Any, float, float]],
        _context: "Render_Context | None" = None,
    ) -> list[dict[str, Any]]:
        """Fetch background tiles from renderer data or auto-generate a floor."""
        render_frame = _render_frame(env)
        env_tiles = render_frame.get("world.background_tiles")
        if env_tiles:
            return list(env_tiles)

        floor_sprite = str(render_frame.get("world.floor_sprite", _DEFAULT_FLOOR))
        bounds_tiles = _floor_tiles_from_bounds(render_frame.get("world.bounds"), floor_sprite)
        if bounds_tiles:
            return bounds_tiles

        inferred_tiles = inferred_floor_tiles(positioned_entities, floor_sprite)
        if inferred_tiles:
            return inferred_tiles

        world_size = render_frame.get("world.size")
        if isinstance(world_size, dict):
            width = int(world_size.get("width", 0))
            height = int(world_size.get("height", 0))
            origin_x = int(world_size.get("origin_x", 0))
            origin_y = int(world_size.get("origin_y", 0))
            return [
                {"x": origin_x + x, "y": origin_y + y, "kind": "floor", "sprite": floor_sprite}
                for x in range(max(0, width))
                for y in range(max(0, height))
            ]
        return []

    def screen_position(
        self,
        entity: Any,
        _env: "Environment",
        _context: "Render_Context | None" = None,
    ) -> tuple[float, float]:
        """Project the position without changing its coordinates."""
        position = getattr(entity, "position", entity)
        x = getattr(position, 'x', None)
        y = getattr(position, 'y', None)
        if x is not None and y is not None:
            return float(x), float(y)
        # Fallback for plain tuple positions: (x, y) or (x, y, z)
        if hasattr(position, '__getitem__') and len(position) >= 2:
            return float(position[0]), float(position[1])
        return 0.0, 0.0

    def prepare_env(self, _env: "Environment", _context: "Render_Context | None" = None) -> None:
        """Grid rendering derives transient visuals at draw time."""
        return None


