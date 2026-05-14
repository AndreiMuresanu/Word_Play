from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from word_play.core import Entity

    from .renderer import Pygame_Renderer, Renderable


def normalize_background_item(item: Any) -> dict[str, Any]:
    """Normalize background tile shorthands into a consistent dict shape."""
    if isinstance(item, dict):
        return item
    if isinstance(item, (tuple, list)) and len(item) >= 3:
        x, y, kind = item[:3]
        color = item[3] if len(item) >= 4 else None
        return {"x": x, "y": y, "kind": kind, "color": color}
    raise TypeError(f"Unsupported background item: {item!r}")


def world_bounds(
    renderer: "Pygame_Renderer",
    background_items: list[dict[str, Any]],
    renderables: list[tuple[int, Entity, Renderable]],
) -> tuple[int, int, int, int]:
    """Compute the visible world bounds from background tiles and entities."""
    xs: list[int] = []
    ys: list[int] = []

    for item in background_items:
        xs.append(int(item["x"]))
        ys.append(int(item["y"]))

    for _, entity, _ in renderables:
        try:
            x, y = renderer.layout.screen_position(entity.position)
        except AttributeError:
            continue
        xs.append(int(x))
        ys.append(int(y))

    if not xs or not ys:
        return 0, 0, 0, 0
    return min(xs), max(xs), min(ys), max(ys)


def screen_rect_for_tile(renderer: "Pygame_Renderer", x: int, y: int, min_x: int, max_y: int) -> tuple[int, int]:
    """Convert a world tile coordinate into the top-left screen pixel."""
    px = renderer.viewport_pad_w + (x - min_x) * renderer.tile_size
    py = renderer.viewport_pad_n + (max_y - y) * renderer.tile_size
    return px, py


def collect_wall_positions(background_items: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """Extract the coordinates of all wall background tiles."""
    return {
        (int(item["x"]), int(item["y"]))
        for item in background_items
        if item.get("kind") == "wall"
    }


def infer_enclosed_floor_positions(
    wall_positions: set[tuple[int, int]],
    occupied_positions: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """Infer enclosed non-wall cells using a boundary flood fill over a finite grid.

    The finite grid is defined by the bounding box of all known occupied positions
    (falling back to walls when no additional occupied positions are provided).
    Non-wall boundary-reachable cells are marked outside; remaining non-wall cells
    are considered interior floor.
    """
    occupied_positions = set(occupied_positions or set())
    bounds_positions = wall_positions | occupied_positions
    if not bounds_positions:
        return set()

    xs = [x for x, _ in bounds_positions]
    ys = [y for _, y in bounds_positions]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    outside: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def maybe_enqueue(x: int, y: int) -> None:
        pos = (x, y)
        if pos in wall_positions or pos in outside:
            return
        outside.add(pos)
        queue.append(pos)

    for x in range(min_x, max_x + 1):
        maybe_enqueue(x, min_y)
        maybe_enqueue(x, max_y)
    for y in range(min_y, max_y + 1):
        maybe_enqueue(min_x, y)
        maybe_enqueue(max_x, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if min_x <= nx <= max_x and min_y <= ny <= max_y:
                maybe_enqueue(nx, ny)

    floors: set[tuple[int, int]] = set()
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            pos = (x, y)
            if pos not in wall_positions and pos not in outside:
                floors.add(pos)

    return floors


def screen_position_for_entity(
    renderer: "Pygame_Renderer",
    entity: "Entity",
    *,
    min_x: int,
    max_y: int,
) -> tuple[int, int] | None:
    """Convert an entity position into its on-screen pixel location."""
    position = getattr(entity, "position", None)
    if position is None:
        return None

    x, y = renderer.layout.screen_position(position)
    return screen_rect_for_tile(renderer, int(x), int(y), min_x, max_y)


def wall_neighbor_mask(x: int, y: int, wall_positions: set[tuple[int, int]]) -> dict[str, bool]:
    """Report which neighboring wall tiles surround a wall cell."""
    return {
        "n": (x, y + 1) in wall_positions,
        "e": (x + 1, y) in wall_positions,
        "s": (x, y - 1) in wall_positions,
        "w": (x - 1, y) in wall_positions,
        "ne": (x + 1, y + 1) in wall_positions,
        "se": (x + 1, y - 1) in wall_positions,
        "sw": (x - 1, y - 1) in wall_positions,
        "nw": (x - 1, y + 1) in wall_positions,
    }


def wall_variant(neighbors: dict[str, bool]) -> str:
    """Classify a wall tile shape from its cardinal connections."""
    cardinal_count = sum(int(neighbors[key]) for key in ("n", "e", "s", "w"))
    if cardinal_count == 4:
        return "cross"
    if cardinal_count == 3:
        return "t_junction"
    if cardinal_count == 2:
        if (neighbors["n"] and neighbors["s"]) or (neighbors["e"] and neighbors["w"]):
            return "straight"
        return "corner"
    if cardinal_count == 1:
        return "end_cap"
    return "pillar"


def wall_connections(neighbors: dict[str, bool]) -> tuple[str, ...]:
    """Convert a neighbor mask into ordered connection direction names."""
    connections: list[str] = []
    if neighbors.get("left", neighbors.get("w", False)):
        connections.append("left")
    if neighbors.get("right", neighbors.get("e", False)):
        connections.append("right")
    if neighbors.get("up", neighbors.get("n", False)):
        connections.append("up")
    if neighbors.get("down", neighbors.get("s", False)):
        connections.append("down")
    return tuple(connections)


def dirs_to_variant(dirs: tuple[str, ...]) -> str:
    """Format a set of directions into the wall sprite variant naming scheme."""
    order = ["left", "right", "up", "down"]
    return "_".join(direction for direction in order if direction in dirs)


def adjacent_wall_variant_name(neighbors: dict[str, bool]) -> str:
    """Pick the sprite variant name implied by adjacent wall connections."""
    connections = wall_connections(neighbors)
    if len(connections) == 0:
        return "flat"
    return dirs_to_variant(connections)
