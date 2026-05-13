"""Room-based graph layout adapter - renders rooms as quadrilaterals."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .layout import Position_Layout_Adapter

if TYPE_CHECKING:
    from word_play.core import Position, Environment


class Room_Graph_Layout_Adapter(Position_Layout_Adapter):
    """Layout adapter for room-based graph environments.

    Renders rooms as filled quadrilaterals with doors between them.
    Can show only current room (one_room_mode=True) or all rooms.
    """

    DOOR_COLOR = (100, 80, 60)
    CORRIDOR_COLOR = (80, 70, 60)

    # Room colors by type
    ROOM_COLORS = {
        "start": (80, 140, 80),  # Green
        "hub": (80, 100, 140),   # Blue-gray
        "treasure": (180, 160, 60),  # Gold
        "goal": (160, 80, 160),  # Purple
        "default": (80, 90, 100),  # Gray
    }

    def __init__(self, one_room_mode: bool = True):
        self._rooms: dict[str, Any] = {}
        self._room_tiles: list[dict[str, Any]] = []
        self._door_tiles: list[dict[str, Any]] = []
        self._one_room_mode = one_room_mode
        self._current_room_id: str | None = None
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

    def prepare_env(self, env: "Environment") -> None:
        """Extract rooms from environment."""
        self._rooms = getattr(env, "room_graph", {})
        self._update_current_room(env)
        self._build_room_background()

    def _update_current_room(self, env: "Environment") -> None:
        """Determine which room agent is currently in."""
        from word_play.presets.movement.room_graph import Room_Position

        agent = getattr(env, "agent", None)
        if agent and hasattr(agent, "position"):
            pos = agent.position
            if isinstance(pos, Room_Position):
                self._current_room_id = pos.room_id
                return
            # Try to find agent in entities
            for entity in getattr(env.state, "entities", []):
                if getattr(entity, "is_agent", False):
                    if isinstance(entity.position, Room_Position):
                        self._current_room_id = entity.position.room_id
                        return
        # Fallback to first room
        if self._rooms:
            self._current_room_id = next(iter(self._rooms.keys()))

    def _get_viewport_room(self) -> Any | None:
        """Get the room currently being viewed."""
        if not self._one_room_mode:
            return None
        if self._current_room_id and self._current_room_id in self._rooms:
            return self._rooms[self._current_room_id]
        return None

    def _calculate_offset(self, room: Any) -> None:
        """Calculate offset to center current room at origin."""
        # Center the room at (0, 0) in viewport
        self._offset_x = -(room.world_x + room.width / 2)
        self._offset_y = -(room.world_y + room.height / 2)

    def _build_room_background(self) -> None:
        """Build background tiles for rooms and doors."""
        self._room_tiles = []
        self._door_tiles = []

        if self._one_room_mode:
            self._build_single_room_background()
        else:
            self._build_all_rooms_background()

    def _build_single_room_background(self) -> None:
        """Build background for only the current room."""
        viewport_room = self._get_viewport_room()
        if not viewport_room:
            return

        self._calculate_offset(viewport_room)

        # Build only the current room
        room = viewport_room
        room_id = self._current_room_id
        room_type = getattr(room, "room_type", "default")
        color = self.ROOM_COLORS.get(room_type, self.ROOM_COLORS["default"])

        # Wall positions (room borders)
        wall_positions: set[tuple[int, int]] = set()
        left = int(room.world_x)
        right = int(room.world_x + room.width - 1)
        top = int(room.world_y)
        bottom = int(room.world_y + room.height)

        # Build walls around perimeter
        for x in range(left, int(room.world_x + room.width)):
            wall_positions.add((x, top))
            wall_positions.add((x, bottom - 1))
        for y in range(top, int(room.world_y + room.height)):
            wall_positions.add((left, y))
            wall_positions.add((right, y))

        # Connected rooms - draw doors
        for connected_id in getattr(room, "connections", set()):
            other = self._rooms.get(connected_id)
            if other:
                door_tiles = self._create_door_tiles(room, other, wall_positions)
                self._door_tiles.extend(door_tiles)

        # Fill room area with floor tiles
        for x in range(left, int(room.world_x + room.width)):
            for y in range(top, int(room.world_y + room.height)):
                if (x, y) not in wall_positions:
                    self._room_tiles.append({
                        "x": float(x) + self._offset_x,
                        "y": float(y) + self._offset_y,
                        "kind": "floor",
                        "sprite": "src/world_tiles/indoors/floors/night_brick_floor_c.png",
                        "color": color,
                        "is_room": True,
                        "room_id": room_id,
                    })

        # Add wall tiles
        wall_set = "src/world_tiles/indoors/wall_sets/bright_brick_wall"
        for x, y in wall_positions:
            self._room_tiles.append({
                "x": float(x) + self._offset_x,
                "y": float(y) + self._offset_y,
                "kind": "wall",
                "wall_set": wall_set,
                "sprite": "",
                "is_wall": True,
            })

    def _build_all_rooms_background(self) -> None:
        """Build background tiles for all rooms and doors."""
        # Track drawn connections
        drawn_doors: set[tuple[str, str]] = set()

        for room_id, room in self._rooms.items():
            # Get room type and color
            room_type = getattr(room, "room_type", "default")
            color = self.ROOM_COLORS.get(room_type, self.ROOM_COLORS["default"])

            # Fill room area with floor tiles
            for x in range(int(room.world_x), int(room.world_x + room.width)):
                for y in range(int(room.world_y), int(room.world_y + room.height)):
                    self._room_tiles.append({
                        "x": float(x),
                        "y": float(y),
                        "kind": "floor",
                        "sprite": "src/world_tiles/misc/floor_directions.png",
                        "color": color,
                        "is_room": True,
                        "room_id": room_id,
                    })

            # Draw doors to connected rooms
            for connected_id in getattr(room, "connections", set()):
                door_key = tuple(sorted([room_id, connected_id]))
                if door_key not in drawn_doors:
                    drawn_doors.add(door_key)
                    other = self._rooms.get(connected_id)
                    if other:
                        self._door_tiles.extend(self._create_door_tiles(room, other))

    def _create_door_tiles(self, room_a: Any, room_b: Any,
                           wall_positions: set[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
        """Create tiles for a door/passage between two rooms."""
        tiles = []

        # Find midpoint between rooms
        mid_x = (room_a.center_x + room_b.center_x) / 2
        mid_y = (room_a.center_y + room_b.center_y) / 2

        if wall_positions is not None:
            # Single room mode: remove wall tiles at door position
            # Determine if horizontal or vertical connection
            dx = abs(room_a.center_x - room_b.center_x)
            dy = abs(room_a.center_y - room_b.center_y)

            if dx > dy:
                # Horizontal connection - door is left/right
                door_y = int(mid_y)
                for door_x in [int(mid_x - 0.5), int(mid_x + 0.5)]:
                    wall_positions.discard((door_x, door_y))
                    tiles.append({
                        "x": float(door_x) + self._offset_x,
                        "y": float(door_y) + self._offset_y,
                        "kind": "floor",
                        "sprite": "src/world_tiles/indoors/floors/night_brick_floor_c.png",
                        "color": self.DOOR_COLOR,
                        "is_door": True,
                    })
            else:
                # Vertical connection - door is up/down
                door_x = int(mid_x)
                for door_y in [int(mid_y - 0.5), int(mid_y + 0.5)]:
                    wall_positions.discard((door_x, door_y))
                    tiles.append({
                        "x": float(door_x) + self._offset_x,
                        "y": float(door_y) + self._offset_y,
                        "kind": "floor",
                        "sprite": "src/world_tiles/indoors/floors/night_brick_floor_c.png",
                        "color": self.DOOR_COLOR,
                        "is_door": True,
                    })
        else:
            # All rooms mode: draw corridor tiles
            # Determine if horizontal or vertical connection
            dx = abs(room_a.center_x - room_b.center_x)
            dy = abs(room_a.center_y - room_b.center_y)

            if dx > dy:
                # Horizontal connection
                for x in range(int(mid_x - 0.5), int(mid_x + 1.5)):
                    tiles.append({
                        "x": float(x),
                        "y": float(mid_y),
                        "kind": "floor",
                        "sprite": "src/world_tiles/misc/floor_directions.png",
                        "color": self.DOOR_COLOR,
                        "is_door": True,
                    })
            else:
                # Vertical connection
                for y in range(int(mid_y - 0.5), int(mid_y + 1.5)):
                    tiles.append({
                        "x": float(mid_x),
                        "y": float(y),
                        "kind": "floor",
                        "sprite": "src/world_tiles/misc/floor_directions.png",
                        "color": self.DOOR_COLOR,
                        "is_door": True,
                    })

        return tiles

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return room and door tiles."""
        # Rebuild if rooms changed or agent moved rooms
        current_rooms = getattr(env, "room_graph", {})
        if current_rooms != self._rooms:
            self._rooms = current_rooms
            self._build_room_background()
        else:
            # Check if agent moved to different room
            prev_room = self._current_room_id
            self._update_current_room(env)
            if self._one_room_mode and prev_room != self._current_room_id:
                self._build_room_background()

        return self._room_tiles + self._door_tiles

    def screen_position(self, position: Position) -> tuple[float, float] | None:
        """Convert room position to screen coordinates."""
        from word_play.presets.movement.room_graph import Room_Position

        if isinstance(position, Room_Position):
            room = self._rooms.get(position.room_id)
            if room:
                if self._one_room_mode:
                    # Return room-relative position
                    return (room.center_x + self._offset_x, room.center_y + self._offset_y)
                return (room.center_x, room.center_y)
            return (0.0, 0.0)
        return None
