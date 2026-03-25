from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from word_play.core import Entity

    from .renderer import PygameRenderer, Renderable


def normalize_background_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if isinstance(item, (tuple, list)) and len(item) >= 3:
        x, y, kind = item[:3]
        color = item[3] if len(item) >= 4 else None
        return {"x": x, "y": y, "kind": kind, "color": color}
    raise TypeError(f"Unsupported background item: {item!r}")


def world_bounds(
    renderer: "PygameRenderer",
    background_items: list[dict[str, Any]],
    renderables: list[tuple[int, Entity, Renderable]],
) -> tuple[int, int, int, int]:
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


def screen_rect_for_tile(renderer: "PygameRenderer", x: int, y: int, min_x: int, max_y: int) -> tuple[int, int]:
    px = renderer.margin + (x - min_x) * renderer.tile_size
    py = renderer.margin + (max_y - y) * renderer.tile_size
    return px, py


def collect_wall_positions(background_items: list[dict[str, Any]]) -> set[tuple[int, int]]:
    return {
        (int(item["x"]), int(item["y"]))
        for item in background_items
        if item.get("kind") == "wall"
    }


def screen_position_for_entity(
    renderer: "PygameRenderer",
    entity: "Entity",
    *,
    min_x: int,
    max_y: int,
) -> tuple[int, int] | None:
    position = getattr(entity, "position", None)
    if position is None:
        return None

    x, y = renderer.layout.screen_position(position)
    return screen_rect_for_tile(renderer, int(x), int(y), min_x, max_y)


def wall_neighbor_mask(x: int, y: int, wall_positions: set[tuple[int, int]]) -> dict[str, bool]:
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
    order = ["left", "right", "up", "down"]
    return "_".join(direction for direction in order if direction in dirs)


def adjacent_wall_variant_name(neighbors: dict[str, bool]) -> str:
    connections = wall_connections(neighbors)
    if len(connections) == 0:
        return "flat"
    return dirs_to_variant(connections)
