from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

from word_play.core import Component, Position

if TYPE_CHECKING:
    from pathlib import Path

    from word_play.core import Action_Selection, Environment



class Renderable(Component):
    """Store sprite and overlay metadata for an entity."""
    def __init__(
        self,
        sprite_path: str,
        z_index: int = 0,
        visible: bool = True,
        overlay_sprite: str | None = None,
        overlay_mode: str = "badge",
        overlay_scale: float | None = None,
        foreground_sprite: str | None = None,
        foreground_scale: float | None = None,
        shadow_scale: float = 0.72,
        bob_amplitude: float = 0.0,
        bob_speed: float = 1.6,
        animation_frames: list[str] | None = None,
        animation_fps: float = 5.0,
        emissive_sprite: str | None = None,
        emissive_intensity: int = 84,
    ):
        super().__init__()
        self.sprite_path = sprite_path
        self.z_index = z_index
        self.visible = visible
        self.overlay_sprite = overlay_sprite
        self.overlay_mode = overlay_mode
        self.overlay_scale = overlay_scale
        self.foreground_sprite = foreground_sprite
        self.foreground_scale = foreground_scale
        self.shadow_scale = shadow_scale
        self.bob_amplitude = bob_amplitude
        self.bob_speed = bob_speed
        self.animation_frames = list(animation_frames or [])
        self.animation_fps = animation_fps
        self.emissive_sprite = emissive_sprite
        self.emissive_intensity = emissive_intensity


class Renderer(ABC):
    @abstractmethod
    def render(self, env: "Environment") -> Any:
        """Render one environment frame using a concrete backend."""


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
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Project the position without changing its coordinates."""
        return float(position.x), float(position.y)


class Environment_Layout_Adapter(Grid_Layout_Adapter):
    """Extend grid layout with environment-provided background tiles."""
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Fetch background tiles or synthesize simple floor/wall backgrounds."""
        wall_positions = getattr(env, "wall_positions", None)
        width = getattr(env, "width", None)
        height = getattr(env, "height", None)
        floor_sprite = getattr(env, "floor_sprite", "src/world_tiles/indoors/floors/day_brick_floor_c.png")
        wall_set = getattr(env, "wall_set", None)
        wall_sprite = getattr(env, "wall_sprite", None)
        if wall_sprite is None:
            for entity in getattr(getattr(env, "state", None), "entities", []):
                if "wall" not in getattr(entity, "tags", []):
                    continue
                renderable = entity.get_component(Renderable) if hasattr(entity, "get_component") else None
                if renderable is not None:
                    wall_sprite = renderable.sprite_path
                    break
        if wall_positions is not None and width is not None and height is not None and floor_sprite and (wall_set or wall_sprite):
            background: list[dict[str, Any]] = []
            for y in range(height):
                for x in range(width):
                    if (x, y) in wall_positions:
                        tile = {"x": x, "y": y, "kind": "wall"}
                        if wall_set:
                            tile["wall_set"] = wall_set
                        else:
                            tile["sprite"] = wall_sprite
                    else:
                        tile = {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                    background.append(tile)
            return background
        background_tiles = getattr(env, "background_tiles", None)
        return [] if background_tiles is None else background_tiles()

    def prepare_env(self, env: "Environment") -> None:
        """Apply common renderer-side sync for inventories, holders, crafters, and containers."""
        try:
            from word_play.presets.systems import Inventory, Crafter, Single_Item_Holder, Container
        except Exception:
            return

        for entity in getattr(getattr(env, "state", None), "entities", []):
            renderable = entity.get_component(Renderable) if hasattr(entity, "get_component") else None
            if renderable is None:
                continue

            inventory = entity.get_component(Inventory)
            holder = entity.get_component(Single_Item_Holder)
            crafter = entity.get_component(Crafter)
            container = entity.get_component(Container)

            if inventory is not None:
                held_item = inventory.inventory[0] if inventory.inventory else None
                held_renderable = None if held_item is None else held_item.get_component(Renderable)
                renderable.overlay_sprite = None if held_renderable is None else held_renderable.sprite_path
                renderable.overlay_mode = "badge"
                renderable.overlay_scale = 0.42
            elif holder is not None and holder.stored_item is not None:
                item_renderable = holder.stored_item.get_component(Renderable)
                if item_renderable is not None:
                    renderable.overlay_sprite = item_renderable.sprite_path
                    renderable.overlay_mode = "center"
                    renderable.overlay_scale = 0.75
            elif crafter is not None:
                if crafter.stored_item is not None:
                    # Output is ready - show the crafted item
                    output_renderable = crafter.stored_item.get_component(Renderable)
                    if output_renderable is not None:
                        renderable.overlay_sprite = output_renderable.sprite_path
                        renderable.overlay_mode = "center"
                        renderable.overlay_scale = 0.75
                elif crafter.active_recipe is not None and crafter.remaining_steps is not None:
                    # Crafting in progress - no overlay needed, just show in HUD
                    renderable.overlay_sprite = None
                else:
                    renderable.overlay_sprite = None

            if "collectable" in entity.tags:
                renderable.visible = "in_inventory" not in entity.tags and "in_container" not in entity.tags

def compact_non_empty_lines(text: str, limit: int = 4) -> list[str]:
    """Return a few non-empty trimmed lines for renderer-side HUD formatting."""
    return [line.strip() for line in text.splitlines() if line.strip()][:limit]


def observation_action_lines(observation: Any) -> list[str]:
    """Return the full numbered list of currently available actions."""
    return [f"[{idx}] {selection}" for idx, selection in enumerate(observation.possible_actions)]


def apply_agent_sidebar(
    env: "Environment",
    *,
    header: str = "Agent",
    reasoning: str | None = None,
    selection: str | None = None,
    observation: Any | None = None,
    action_lines: list[str] | None = None,
    max_reasoning_lines: int = 32,
    max_selection_lines: int = 4,
    max_action_lines: int = 12,
) -> None:
    """Populate renderer-facing sidebar fields from raw agent UI state."""
    reasoning_lines = ["Agent Thought Process:"]
    if reasoning:
        reasoning_lines.extend([line for line in str(reasoning).splitlines() if line.strip()])
    else:
        reasoning_lines.append("(no explicit reasoning returned)")

    chosen_action_lines = ["Chosen Action:"]
    chosen_action_lines.append(str(selection) if selection else "(no action chosen yet)")

    resolved_action_lines = list(action_lines or [])
    if observation is not None and not resolved_action_lines:
        resolved_action_lines = observation_action_lines(observation)
    sidebar_action_lines = ["Possible Actions:"]
    sidebar_action_lines.extend(resolved_action_lines or ["(no actions available)"])

    env.hud_sidebar_header = header
    env.hud_sidebar_lines = reasoning_lines[:max_reasoning_lines]
    env.hud_sidebar_selected_action = chosen_action_lines[:max_selection_lines]
    env.hud_sidebar_actions = sidebar_action_lines[:max_action_lines]


def apply_policy_selection_sidebar(
    env: "Environment",
    *,
    observation: Any,
    selection: Any,
    info: dict[str, Any] | None = None,
    header: str = "Agent",
    max_reasoning_lines: int = 32,
    max_selection_lines: int = 4,
    max_action_lines: int = 12,
) -> None:
    """Populate sidebar state from a generic policy selection result."""
    resolved_info = info or {}
    apply_agent_sidebar(
        env,
        header=header,
        reasoning=resolved_info.get("reasoning"),
        selection=str(selection),
        observation=observation,
        max_reasoning_lines=max_reasoning_lines,
        max_selection_lines=max_selection_lines,
        max_action_lines=max_action_lines,
    )


from .draw import render_environment
from .replay_and_live import replay_frames, replay_recording, run_live_view
from .runtime import configure_renderer, init_pygame_if_needed


class Pygame_Renderer(Renderer):
    """Concrete renderer that delegates drawing and replay to pygame helpers."""
    def __init__(
        self,
        layout: Position_Layout_Adapter,
        tile_size: int = 32,
        draw_grid_overlay: bool = False,
    ):
        """Configure renderer state, layout mapping, and sizing defaults."""
        configure_renderer(
            self,
            layout=layout,
            tile_size=tile_size,
            draw_grid_overlay=draw_grid_overlay,
        )

    def render(self, env: "Environment") -> None:
        """Initialize pygame if needed and draw the current environment."""
        init_pygame_if_needed(self)
        render_environment(self, env)

    def replay_frames(
        self,
        frames: list[dict[str, Any]],
        *,
        autoplay: bool = False,
        step_delay: float = 0.28,
    ) -> None:
        """Play back an in-memory list of recorded frames."""
        replay_frames(self, frames, autoplay=autoplay, step_delay=step_delay)

    def replay_recording(
        self,
        log_path: str | "Path",
        *,
        autoplay: bool = False,
        step_delay: float = 0.28,
    ) -> None:
        """Load a saved recording from disk and replay it."""
        replay_recording(self, log_path, autoplay=autoplay, step_delay=step_delay)

    def run_live_view(
        self,
        env: "Environment",
        *,
        step_builder: Callable[["Environment"], list["Action_Selection"]],
        recorder: Any | None = None,
        keep_logs: bool = True,
        log_path: str | "Path" | None = None,
        log_root: str | "Path" | None = None,
        record_title: str = "Environment Replay",
        record_metadata: dict[str, Any] | None = None,
        autoplay: bool = True,
        step_delay: float = 0.28,
        max_steps: int | None = None,
        reset_factory: Callable[[], "Environment"] | None = None,
        initial_notes: list[str] | None = None,
        autofill_required_kwargs: Callable[["Action_Selection"], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run an interactive live view that can step and record an environment."""
        return run_live_view(
            self,
            env,
            step_builder=step_builder,
            recorder=recorder,
            keep_logs=keep_logs,
            log_path=log_path,
            log_root=log_root,
            record_title=record_title,
            record_metadata=record_metadata,
            autoplay=autoplay,
            step_delay=step_delay,
            max_steps=max_steps,
            reset_factory=reset_factory,
            initial_notes=initial_notes,
            autofill_required_kwargs=autofill_required_kwargs,
        )


def render(
    env: "Environment",
    *,
    renderer: Pygame_Renderer | None = None,
    tile_size: int = 32,
    draw_grid_overlay: bool = False,
) -> Pygame_Renderer:
    """Render one frame with a provided or auto-created pygame renderer."""
    active_renderer = renderer or getattr(env, "renderer_impl", None)
    if active_renderer is None:
        active_renderer = Pygame_Renderer(
            layout=Environment_Layout_Adapter(),
            tile_size=tile_size,
            draw_grid_overlay=draw_grid_overlay,
        )
    active_renderer.render(env)
    return active_renderer


def replay(
    log_path: str | "Path",
    *,
    tile_size: int = 32,
    draw_grid_overlay: bool = False,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Replay a saved log using the default environment layout adapter."""
    renderer = Pygame_Renderer(
        layout=Environment_Layout_Adapter(),
        tile_size=tile_size,
        draw_grid_overlay=draw_grid_overlay,
    )
    renderer.replay_recording(log_path, autoplay=autoplay, step_delay=step_delay)
