from __future__ import annotations

from abc import ABC, abstractmethod
import math
from typing import Any

from word_play.core import Environment, Position
from word_play.presets.movement.single_point import Single_Point_Position
from word_play.presets.systems import Inventory

from .renderer import Renderable
from .wall_geometry import infer_enclosed_floor_positions


def _inventory_items(inventory: Any) -> list[Any]:
    """Return items from either the legacy inventory list or newer contents list."""
    items = getattr(inventory, "contents", None)
    if items is None:
        items = getattr(inventory, "inventory", [])
    return list(items or [])


def _is_in_any_inventory(item, env) -> bool:
    """Check if item is in any entity's inventory."""
    for entity in env.state.entities:
        inventory = entity.get_component(Inventory)
        if inventory and item in _inventory_items(inventory):
            return True
    return False


class Position_Layout_Adapter(ABC):
    """Map environment positions and optional backgrounds into render space."""
    @abstractmethod
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert a world position into renderer grid coordinates."""

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return background tiles to draw behind entities."""
        return []

    def prepare_env(self, env: "Environment") -> None:
        """Update any renderer-facing derived state before drawing."""
        return None


class Grid_Layout_Adapter(Position_Layout_Adapter):
    """Use entity x/y values directly as grid coordinates."""
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return empty - backgrounds are handled by renderer."""
        return []

    def screen_position(self, position: Position | Any) -> tuple[float, float]:
        """Project the position without changing its coordinates."""
        x = getattr(position, 'x', None)
        y = getattr(position, 'y', None)
        if x is not None and y is not None:
            return float(x), float(y)
        # Fallback for plain tuple positions: (x, y) or (x, y, z)
        if hasattr(position, '__getitem__') and len(position) >= 2:
            return float(position[0]), float(position[1])
        return 0.0, 0.0


def _get_slot_offsets(n: int, radius: float) -> list[tuple[float, float]]:
    """Return predefined visual offsets for n entities at a single point.

    Layouts:
    - 1 entity: center
    - 2 entities: left/right
    - 3 entities: triangle (top + bottom corners)
    - 4 entities: compass layout (N, E, S, W)
    - 5-8: evenly distributed ring
    - 9+: concentric rings
    """
    if n == 1:
        return [(0.0, 0.0)]
    elif n == 2:
        # Left and right
        d = radius
        return [(-d, 0.0), (d, 0.0)]
    elif n == 3:
        # Triangle pointing up
        r = radius
        return [
            (0.0, -r),                    # Top
            (r * 0.866, r * 0.5),       # Bottom-right
            (-r * 0.866, r * 0.5),      # Bottom-left
        ]
    elif n == 4:
        # Compass layout (N, E, S, W) - classic "sharing a tile" look
        r = radius
        return [
            (0.0, -r),    # North (top)
            (r, 0.0),     # East (right)
            (0.0, r),     # South (bottom)
            (-r, 0.0),    # West (left)
        ]
    elif n <= 8:
        # Ring layout - evenly spaced around circle
        offsets = []
        for i in range(n):
            # Start at top, go clockwise
            angle = -math.pi / 2 + (2 * math.pi * i / n)
            offsets.append((
                radius * math.cos(angle),
                radius * math.sin(angle) * 0.7,  # Flatten Y for perspective
            ))
        return offsets
    else:
        # Concentric rings for large groups
        offsets = []
        ring_size = 8  # entities per outer ring
        for i in range(n):
            ring = i // ring_size
            index_in_ring = i % ring_size

            # Inner entities are closer, outer are further
            r = radius * (1 + ring * 0.5)
            angle = -math.pi / 2 + (2 * math.pi * index_in_ring / ring_size)
            offsets.append((
                r * math.cos(angle),
                r * math.sin(angle) * 0.7,
            ))
        return offsets


class SinglePointLayout(Position_Layout_Adapter):
    """Unified layout for entities at a single point position.

    Entities can be arranged in:
    - "compass" mode: N/E/S/W for up to 4, expanding to rings for more
    - "circle" mode: Circular arrangement with configurable radius

    Optional room background can be generated when include_room=True.
    """

    # Room background settings
    WALL_SET = "src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall"
    TABLE_SPRITE = "src/world_tiles/indoors/stations/prep_table.png"
    DEFAULT_FLOOR = "src/world_tiles/indoors/floors/day_brick_floor_c.png"

    def __init__(
        self,
        center_x: float = 0,
        center_y: float = 0,
        radius: float = 0.35,
        layout_mode: str = "compass",  # "compass" or "circle"
        include_room: bool = False,
        only_agents: bool = False,
    ):
        """
        Args:
            center_x, center_y: The grid coordinates of the center point
            radius: Base radius for positioning in tile units
            layout_mode: "compass" (N/E/S/W slots) or "circle" (pure circular)
            include_room: If True, generate room walls and floor tiles
            only_agents: If True, only position agents (ignore non-agent entities)
        """
        self.base_x = center_x
        self.base_y = center_y
        self.radius = radius
        self.base_radius = radius
        self.layout_mode = layout_mode
        self.include_room = include_room
        self.only_agents = only_agents
        self._cached_background: list[dict[str, Any]] | None = None
        self.room_width = 5
        self.room_height = 5

    def _calculate_room_size(self, n_agents: int) -> tuple[int, int]:
        """Calculate room size based on agent count."""
        if n_agents <= 4:
            return 5, 5
        elif n_agents <= 8:
            return 7, 7
        elif n_agents <= 12:
            return 9, 7
        else:
            return 11, 9

    @staticmethod
    def _get_floor_sprite() -> str:
        """Get a nice floor sprite."""
        return SinglePointLayout.DEFAULT_FLOOR

    def prepare_env(self, env: "Environment") -> None:
        """Calculate visual positions for entities at this point."""
        if env is None:
            return

        entities = list(getattr(env.state, "entities", []))

        # Filter entities to position
        if self.only_agents:
            positioned_entities = [e for e in entities if getattr(e, "is_agent", False)]
        else:
            positioned_entities = [
                e for e in entities
                if isinstance(getattr(e, "position", None), Single_Point_Position)
            ]

        n = len(positioned_entities)
        if n == 0:
            return

        # Sort for stable ordering: agents first, then by name
        positioned_entities.sort(key=lambda e: (
            0 if getattr(e, "is_agent", False) else 1,
            e.name,
        ))

        # Calculate room size if needed
        agent_count = len([e for e in positioned_entities if getattr(e, "is_agent", False)])
        if self.include_room and agent_count > 0:
            self.room_width, self.room_height = self._calculate_room_size(agent_count)
            self._cached_background = None

        # Calculate offsets based on layout mode
        if self.layout_mode == "compass":
            offsets = _get_slot_offsets(n, self.radius)
        else:  # circle
            offsets = []
            for i in range(n):
                angle = -math.pi / 2 + (2 * math.pi * i / n)
                offsets.append((
                    self.base_radius * math.cos(angle),
                    self.base_radius * math.sin(angle) * 0.7,
                ))

        # Assign offsets to each entity
        for entity, (offset_x, offset_y) in zip(positioned_entities, offsets):
            pos = entity.position
            if isinstance(pos, Single_Point_Position):
                pos.visual_offset_x = offset_x
                pos.visual_offset_y = offset_y

    def background(self, env: "Environment" | None) -> list[dict[str, Any]]:
        """Generate optional room background with walls and flooring."""
        if not self.include_room:
            return []

        if self._cached_background is not None:
            return self._cached_background

        if env is None:
            return []

        entities = list(getattr(env.state, "entities", []))
        agent_count = len([e for e in entities if getattr(e, "is_agent", False)])
        if agent_count == 0:
            return []

        room_w, room_h = self._calculate_room_size(agent_count)
        tiles = []

        half_w = room_w // 2
        half_h = room_h // 2

        # Generate interior floor tiles
        for y in range(-half_h, half_h + 1):
            for x in range(-half_w, half_w + 1):
                abs_x = self.base_x + x
                abs_y = self.base_y + y

                if x == 0 and y == 0:
                    # Meeting table at center
                    tiles.append({
                        "x": abs_x,
                        "y": abs_y,
                        "kind": "floor",
                        "sprite": self.TABLE_SPRITE,
                    })
                else:
                    tiles.append({
                        "x": abs_x,
                        "y": abs_y,
                        "kind": "floor",
                        "sprite": self._get_floor_sprite(),
                    })

        # Generate walls OUTSIDE the room
        wall_w = half_w + 1
        wall_h = half_h + 1

        for y in range(-wall_h, wall_h + 1):
            for x in range(-wall_w, wall_w + 1):
                is_outer_ring = (y == -wall_h or y == wall_h or x == -wall_w or x == wall_w)
                if not is_outer_ring:
                    continue

                abs_x = self.base_x + x
                abs_y = self.base_y + y

                tiles.append({
                    "x": abs_x,
                    "y": abs_y,
                    "kind": "wall",
                    "wall_set": self.WALL_SET,
                })

        self._cached_background = tiles
        return tiles

    def screen_position(self, position: Position | Any) -> tuple[float, float]:
        """Convert position to screen coordinates."""
        if isinstance(position, Single_Point_Position):
            offset_x = getattr(position, "visual_offset_x", 0.0)
            offset_y = getattr(position, "visual_offset_y", 0.0)
            return (self.base_x + offset_x, self.base_y + offset_y)

        # Fallback: try to get x/y attributes, default to center
        if position is not None:
            x = getattr(position, "x", None)
            y = getattr(position, "y", None)
            if x is not None and y is not None:
                return (float(x), float(y))

        return (self.base_x, self.base_y)


Circle_Layout_Adapter = SinglePointLayout


_DEFAULT_FLOOR = "src/world_tiles/indoors/floors/day_brick_floor_c.png"


class Environment_Layout_Adapter(Grid_Layout_Adapter):
    """Grid layout that fetches background tiles from env or renderer."""
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Fetch background tiles from env.background_tiles, then renderer, or auto-generate floor."""
        env_tiles = getattr(env, "background_tiles", None)
        if env_tiles:
            return list(env_tiles)
        # Auto-generate floor from self.floor_sprite + width/height
        floor_sprite = getattr(env, "floor_sprite", None) or _DEFAULT_FLOOR
        w = getattr(env, "width", 0)
        h = getattr(env, "height", 0)
        if w > 0 and h > 0:
            return [{"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                    for x in range(w) for y in range(h)]
        wall_positions = {
            (int(entity.position.x), int(entity.position.y))
            for entity in getattr(getattr(env, "state", None), "entities", [])
            if getattr(entity, "position", None) is not None
            and "wall" in getattr(entity, "tags", [])
            and hasattr(entity.position, "x")
            and hasattr(entity.position, "y")
        }
        if wall_positions:
            occupied_positions = {
                (int(entity.position.x), int(entity.position.y))
                for entity in getattr(getattr(env, "state", None), "entities", [])
                if getattr(entity, "position", None) is not None
                and hasattr(entity.position, "x")
                and hasattr(entity.position, "y")
            }
            inferred_tiles = [
                {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                for x, y in sorted(infer_enclosed_floor_positions(wall_positions, occupied_positions))
            ]
            if inferred_tiles:
                return inferred_tiles
        renderer = getattr(env, "renderer_impl", None)
        if renderer is not None and hasattr(renderer, "background_tiles"):
            return renderer.background_tiles()
        return []

    def prepare_env(self, env: "Environment") -> None:
        """Apply common renderer-side sync for inventory overlays and collectable visibility."""
        for entity in getattr(getattr(env, "state", None), "entities", []):
            renderable = entity.get_component(Renderable) if hasattr(entity, "get_component") else None
            if renderable is None:
                continue

            inventory = entity.get_component(Inventory)

            if inventory is not None:
                inventory_items = _inventory_items(inventory)
                held_item = inventory_items[0] if inventory_items else None
                held_renderable = None if held_item is None else held_item.get_component(Renderable)
                renderable.overlay_sprite = None if held_renderable is None else held_renderable.sprite_path
                renderable.overlay_mode = "badge"
                renderable.overlay_scale = 0.28
            else:
                renderable.overlay_sprite = None

            if "collectable" in entity.tags:
                renderable.visible = not _is_in_any_inventory(entity, env)
