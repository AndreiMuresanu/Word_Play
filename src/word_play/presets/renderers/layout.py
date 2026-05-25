from __future__ import annotations

from abc import ABC, abstractmethod
import math
import re
from types import MethodType
from typing import Any

from word_play.core import Environment, Position
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.movement.single_point import Single_Point_Position
from word_play.presets.systems import Inventory
from word_play.presets.systems.communication import Communication_Policy
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import (
    Human_Communication_Policy,
)

from .renderer import Renderable
from .runtime import prompt_human_action, prompt_human_multi_select, prompt_human_text
from .wall_geometry import infer_enclosed_floor_positions

try:
    from word_play.presets.movement.continuous_2d import Continuous_Position_2D
except ImportError:
    Continuous_Position_2D = None

try:
    from word_play.presets.movement.graph import Graph_Position
except ImportError:
    Graph_Position = None

try:
    from word_play.presets.systems import Container
except ImportError:
    Container = None

try:
    from word_play.presets.systems import Crafter
except ImportError:
    Crafter = None

try:
    from word_play.presets.systems import Single_Item_Holder
except ImportError:
    Single_Item_Holder = None

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


def _is_in_closed_container(item, env) -> bool:
    """Check if item is in a hidden/closed container."""
    if Container is None:
        return False
    for entity in env.state.entities:
        container = entity.get_component(Container)
        if container and item in _inventory_items(container):
            if container.visibility == "hidden" and not container.is_open:
                return True
    return False


def _install_renderer_conversation_transcript_hooks(env) -> None:
    """Attach renderer-only chat bookkeeping to communication policies.

    Communication policies still own the actual conversation behavior. These
    wrappers only copy outgoing messages into ``Renderable.last_message`` for
    speech bubbles and keep a short transcript for human chat prompts.
    """
    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue
        renderable = entity.get_component(Renderable)
        policy = entity.get_component(Communication_Policy)
        if renderable is None or policy is None:
            continue
        if getattr(policy, "_renderer_message_hook_installed", False):
            continue

        original_start = policy.start_conversation
        original_send = policy.send_message
        original_end = policy.end_conversation

        def wrapped_start(self, participants, env, info=None, *, _original=original_start):
            depth = int(getattr(env, "_renderer_conversation_depth", 0))
            if depth == 0:
                env._renderer_conversation_log = []
                env._renderer_conversation_participants = [participant.name for participant in participants]
                starter_name = getattr(getattr(self, "entity", None), "name", "Unknown")
                env._renderer_conversation_starter = starter_name
                env._renderer_conversation_log.append(f"Conversation started by {starter_name}")
            env._renderer_conversation_depth = depth + 1
            return _original(participants, env, info)

        def wrapped_send(self, recipients, env, info=None, *, _original=original_send, _renderable=renderable):
            message = _original(recipients, env, info)
            if message is not None:
                _renderable.last_message = str(message)
                _renderable._last_message_step = getattr(env, "cur_step", 0)
                conversation_log = list(getattr(env, "_renderer_conversation_log", []))
                speaker_name = getattr(getattr(self, "entity", None), "name", "Unknown")
                participant_count = max(1, len(getattr(env, "_renderer_conversation_participants", [])))
                prior_messages = max(
                    0,
                    len([entry for entry in conversation_log if entry.startswith("Round ") and ": " in entry])
                )
                round_number = prior_messages // participant_count + 1
                conversation_log.append(f"Round {round_number} - {speaker_name}: {message}")
                env._renderer_conversation_log = conversation_log[-8:]
            return message

        def wrapped_end(self, participants, env, info=None, *, _original=original_end):
            try:
                return _original(participants, env, info)
            finally:
                depth = max(0, int(getattr(env, "_renderer_conversation_depth", 0)) - 1)
                env._renderer_conversation_depth = depth
                if depth == 0:
                    env._renderer_conversation_participants = []
                    env._renderer_conversation_log = []
                    env._renderer_conversation_starter = None

        policy.start_conversation = MethodType(wrapped_start, policy)
        policy.send_message = MethodType(wrapped_send, policy)
        policy.end_conversation = MethodType(wrapped_end, policy)
        policy._renderer_message_hook_installed = True


def _expire_render_messages(env) -> None:
    """Clear transient speech bubbles after they have been visible for one step."""
    current_step = getattr(env, "cur_step", 0)
    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue
        renderable = entity.get_component(Renderable)
        if renderable is None:
            continue
        message_step = getattr(renderable, "_last_message_step", None)
        if message_step is None:
            continue
        if current_step > message_step + 1:
            renderable.last_message = None
            renderable._last_message_step = None


def _install_renderer_human_input_hooks(env) -> None:
    """Route human action and chat prompts through the renderer HUD.

    The existing human policies prompt through stdin. When an environment is
    actively rendered, these wrappers swap only the prompt surface so keyboard
    input can stay inside the pygame window.
    """
    renderer = getattr(env, "renderer_impl", None)
    if renderer is None:
        return

    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue

        if Human_Takes_Action is not None:
            action_policy = entity.get_component(Human_Takes_Action)
            if action_policy is not None and not getattr(action_policy, "_renderer_prompt_hook_installed", False):
                original_choose = action_policy._choose_action
                original_kwargs = action_policy._get_action_kwargs

                def wrapped_choose(self, observation, *, _original=original_choose):
                    active_renderer = getattr(observation.possible_actions[0].env, "renderer_impl", None) if observation.possible_actions else None
                    if active_renderer is None:
                        return _original(observation)
                    return prompt_human_action(active_renderer, observation.possible_actions[0].env, observation)

                def wrapped_kwargs(self, action_selection, *, _original=original_kwargs):
                    active_renderer = getattr(action_selection.env, "renderer_impl", None)
                    if active_renderer is None:
                        return _original(action_selection)
                    error_message = None
                    while True:
                        if (
                            action_selection.required_kwargs
                            and len(action_selection.required_kwargs) == 1
                        ):
                            arg_name, arg = next(iter(action_selection.required_kwargs.items()))
                            arg_description = arg.arg_description(
                                action_selection.actor,
                                action_selection.target_entity,
                                action_selection.env,
                            )
                            matches = re.findall(r"(\d+)\s*\(([^)]+)\)", arg_description)
                            if matches:
                                text = prompt_human_multi_select(
                                    active_renderer,
                                    action_selection.env,
                                    entity_name=action_selection.actor.name,
                                    position_label=str(action_selection.actor.position),
                                    header="Action Arguments",
                                    instructions=[
                                        str(action_selection),
                                        f"Choose values for: {arg_name}",
                                        "Use Up/Down to move, Space to toggle, Enter to submit.",
                                        *([f"Error: {error_message}"] if error_message else []),
                                    ],
                                    options=[(int(idx), label) for idx, label in matches],
                                )
                                try:
                                    return action_selection.parse_and_validate_kwarg_list(text)
                                except Exception as exc:
                                    error_message = str(exc)
                                    continue

                        instructions = [
                            str(action_selection),
                            "Type the required values separated by ';'.",
                            "Press Enter to submit.",
                        ]
                        if action_selection.required_kwargs:
                            for name, arg in action_selection.required_kwargs.items():
                                instructions.append(
                                    f'{name}: {arg.arg_description(action_selection.actor, action_selection.target_entity, action_selection.env)}'
                                )
                        if error_message:
                            instructions.append(f"Error: {error_message}")

                        text = prompt_human_text(
                            active_renderer,
                            action_selection.env,
                            entity_name=action_selection.actor.name,
                            position_label=str(action_selection.actor.position),
                            header="Action Arguments",
                            instructions=instructions,
                        )
                        try:
                            return action_selection.parse_and_validate_kwarg_list(text)
                        except Exception as exc:
                            error_message = str(exc)

                action_policy._choose_action = MethodType(wrapped_choose, action_policy)
                action_policy._get_action_kwargs = MethodType(wrapped_kwargs, action_policy)
                action_policy._renderer_prompt_hook_installed = True

        if Human_Communication_Policy is not None:
            comm_policy = entity.get_component(Human_Communication_Policy)
            if comm_policy is not None and not getattr(comm_policy, "_renderer_prompt_hook_installed", False):
                original_send = comm_policy.send_message

                def wrapped_send(self, recipients, env, info=None, *, _original=original_send):
                    active_renderer = getattr(env, "renderer_impl", None)
                    if active_renderer is None or self.entity is None:
                        return _original(recipients, env, info)
                    recipient_names = ", ".join(recipient.name for recipient in recipients) or "nobody"
                    transcript = list(getattr(env, "_renderer_conversation_log", []))
                    instructions = [
                        f"Recipients: {recipient_names}",
                        *([str(info)] if info else []),
                    ]
                    if transcript:
                        instructions.append("Conversation so far:")
                        instructions.extend(transcript[-6:])
                    instructions.extend([
                        f"Now speaking: {self.entity.name}",
                        "Type your message.",
                        "Press Enter to send.",
                    ])
                    return prompt_human_text(
                        active_renderer,
                        env,
                        entity_name=self.entity.name,
                        position_label=str(self.entity.position),
                        header="Chat",
                        instructions=instructions,
                    )

                comm_policy.send_message = MethodType(wrapped_send, comm_policy)
                comm_policy._renderer_prompt_hook_installed = True


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


# Backward-compatible alias (deprecated, use SinglePointLayout)
Circle_Layout_Adapter = SinglePointLayout


class Graph_Layout_Adapter(Position_Layout_Adapter):
    """Layout adapter for graph-based environments.

    Renders nodes at their (x,y) coordinates with visible connections.
    Supports different room types: start, hub, treasure, goal.
    """

    NODE_SIZE = 0.4
    EDGE_COLOR = (60, 70, 80)

    # Colors for different room types
    ROOM_COLORS = {
        "start": (100, 180, 100),    # Green - start room
        "hub": (140, 140, 180),      # Blue-gray - hub
        "treasure": (200, 180, 80),  # Gold - treasure room
        "goal": (180, 100, 180),     # Purple - goal room
        "default": (120, 140, 160), # Default blue-gray
    }

    def __init__(self):
        self._graph_nodes: dict[str, Any] = {}
        self._edge_tiles: list[dict[str, Any]] = []
        self._node_tiles: list[dict[str, Any]] = []

    def prepare_env(self, env: "Environment") -> None:
        """Extract graph nodes and edges from environment."""
        self._graph_nodes = getattr(env, "graph_nodes", {})
        self._build_graph_background()

    def _build_graph_background(self) -> None:
        """Build background tiles for graph edges and nodes."""
        self._edge_tiles = []
        self._node_tiles = []

        # Build edges from node connections
        drawn_edges: set[tuple[str, str]] = set()
        for node_id, node in self._graph_nodes.items():
            # Draw connections as edges
            for connected_id in getattr(node, "connections", set()):
                # Avoid drawing edges twice
                edge_key = tuple(sorted([node_id, connected_id]))
                if edge_key in drawn_edges:
                    continue
                drawn_edges.add(edge_key)

                other = self._graph_nodes.get(connected_id)
                if other:
                    self._edge_tiles.extend(self._create_edge_tiles(node, other))

            # Draw node itself with color based on room type
            room_type = getattr(node, "room_type", "default")
            node_color = self.ROOM_COLORS.get(room_type, self.ROOM_COLORS["default"])

            self._node_tiles.append({
                "x": node.x,
                "y": node.y,
                "kind": "floor",
                "sprite": "src/world_tiles/misc/floor_directions.png",
                "color": node_color,
                "is_node": True,
                "node_id": node_id,
                "room_type": room_type,
            })

    def _create_edge_tiles(self, node_a: Any, node_b: Any) -> list[dict[str, Any]]:
        """Create tiles to draw a line between two nodes."""
        tiles = []
        x1, y1 = node_a.x, node_a.y
        x2, y2 = node_b.x, node_b.y

        # Draw intermediate tiles along the edge
        dx = x2 - x1
        dy = y2 - y1
        dist = (dx * dx + dy * dy) ** 0.5

        if dist > 0:
            steps = int(dist * 2)  # 2 tiles per unit distance
            for i in range(steps + 1):
                t = i / max(steps, 1)
                x = x1 + dx * t
                y = y1 + dy * t
                tiles.append({
                    "x": x,
                    "y": y,
                    "kind": "floor",
                    "sprite": "src/world_tiles/misc/floor_directions.png",
                    "color": self.EDGE_COLOR,
                    "is_edge": True,
                })
        return tiles

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return graph edges and nodes as background tiles."""
        # Rebuild if nodes changed
        current_nodes = getattr(env, "graph_nodes", {})
        if current_nodes != self._graph_nodes:
            self._graph_nodes = current_nodes
            self._build_graph_background()
        return self._edge_tiles + self._node_tiles

    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert graph position to screen coordinates."""
        if Graph_Position is not None and isinstance(position, Graph_Position):
            node = self._graph_nodes.get(position.node_id)
            if node:
                return (float(node.x), float(node.y))
            return (0.0, 0.0)
        return super().screen_position(position)

class Continuous_2D_Layout_Adapter(Grid_Layout_Adapter):
    """Adapter for continuous 2D positions (float coordinates) with camera support.

    Also handles background tiles from environment with camera viewport clamping.
    """

    def __init__(self, viewport_width: int = 15, viewport_height: int = 15):
        super().__init__()
        self.camera_offset_x: float = 0
        self.camera_offset_y: float = 0
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

    def prepare_env(self, env: "Environment") -> None:
        """Update camera position based on player position."""
        # Find the player/agent entity
        player = getattr(env, "player", None)
        if player is None and hasattr(env, "agents") and env.agents:
            player = env.agents[0]

        if player is not None and hasattr(player, "position"):
            pos = player.position
            if Continuous_Position_2D is not None and isinstance(pos, Continuous_Position_2D):
                # Center camera on player: player_x - half_viewport
                half_view = self.viewport_width / 2
                target_camera = pos.x - half_view

                # Clamp to world bounds
                bounds_min_x = getattr(env, "bounds_min_x", 0)
                bounds_max_x = getattr(env, "bounds_max_x", target_camera + self.viewport_width)
                max_cam = max(bounds_min_x, bounds_max_x - self.viewport_width)

                self.camera_offset_x = max(bounds_min_x, min(target_camera, max_cam))
            else:
                self.camera_offset_x = getattr(env, "camera_x", 0)
        else:
            self.camera_offset_x = getattr(env, "camera_x", 0)

        self.camera_offset_y = getattr(env, "camera_offset_y", 0)

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Fetch background tiles from renderer and filter to visible viewport."""
        renderer = getattr(env, "renderer_impl", None)
        if renderer is None or not hasattr(renderer, "background_tiles"):
            return []
        all_tiles = renderer.background_tiles()

        # Filter to visible viewport (camera area + margin)
        margin = 2  # Extra tiles on each side for smooth scrolling
        visible_tiles = []

        for tile in all_tiles:
            tx = float(tile.get("x", 0))
            ty = float(tile.get("y", 0))

            # Check if tile is within camera viewport (y check too)
            if (self.camera_offset_x - margin <= tx <=
                self.camera_offset_x + self.viewport_width + margin and
                self.camera_offset_y - margin <= ty <=
                self.camera_offset_y + self.viewport_height + margin):
                # Apply camera transform to tile position (world -> screen)
                visible_tiles.append({
                    **tile,
                    "x": tx - self.camera_offset_x,
                    "y": ty - self.camera_offset_y,
                })

        return visible_tiles

    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert continuous position to screen coordinates with camera offset."""
        if Continuous_Position_2D is not None and isinstance(position, Continuous_Position_2D):
            return (
                float(position.x) - self.camera_offset_x,
                float(position.y) - self.camera_offset_y,
            )

        return super().screen_position(position)


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
        """Apply common renderer-side sync for inventories, holders, crafters, and containers."""
        _install_renderer_human_input_hooks(env)
        _install_renderer_conversation_transcript_hooks(env)
        _expire_render_messages(env)

        for entity in getattr(getattr(env, "state", None), "entities", []):
            renderable = entity.get_component(Renderable) if hasattr(entity, "get_component") else None
            if renderable is None:
                continue

            inventory = entity.get_component(Inventory)
            holder = entity.get_component(Single_Item_Holder) if Single_Item_Holder is not None else None
            crafter = entity.get_component(Crafter) if Crafter is not None else None
            container = entity.get_component(Container) if Container is not None else None

            if inventory is not None:
                inventory_items = _inventory_items(inventory)
                held_item = inventory_items[0] if inventory_items else None
                held_renderable = None if held_item is None else held_item.get_component(Renderable)
                renderable.overlay_sprite = None if held_renderable is None else held_renderable.sprite_path
                renderable.overlay_mode = "badge"
                renderable.overlay_scale = 0.28
            elif holder is not None and holder.stored_item is not None:
                item_renderable = holder.stored_item.get_component(Renderable)
                if item_renderable is not None:
                    renderable.overlay_sprite = item_renderable.sprite_path
                    renderable.overlay_mode = "center"
                    renderable.overlay_scale = 0.75
            elif crafter is not None:
                if crafter.output_item is not None:
                    # Output is ready - show the crafted item
                    output_renderable = crafter.output_item.get_component(Renderable)
                    if output_renderable is not None:
                        renderable.overlay_sprite = output_renderable.sprite_path
                        renderable.overlay_mode = "center"
                        renderable.overlay_scale = 0.75
                elif crafter.active_recipe is not None and crafter.remaining_steps is not None:
                    # Crafting in progress - no overlay needed, just show in HUD
                    renderable.overlay_sprite = None
                else:
                    renderable.overlay_sprite = None
            else:
                renderable.overlay_sprite = None

            if "collectable" in entity.tags:
                renderable.visible = not _is_in_any_inventory(entity, env) and not _is_in_closed_container(entity, env)
