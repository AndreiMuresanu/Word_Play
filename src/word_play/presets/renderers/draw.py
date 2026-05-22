from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity
from word_play.presets.systems.containers import Container, Single_Item_Holder
from word_play.presets.systems.crafter import Crafter
from word_play.presets.systems.communication.trade_communication.trade_actions import Public_Trade_Offer
from word_play.presets.systems.inventory import Inventory

from .assets import get_or_load_image, get_scaled_image, resolve_wall_sprite
from .focus import focus_radius, set_focus_from_click
from .wall_geometry import collect_wall_positions, normalize_background_item, screen_rect_for_tile, wall_neighbor_mask, world_bounds
from .renderer import Renderable
from .runtime import apply_renderer_metrics, ensure_screen_size, fitted_tile_size

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import Pygame_Renderer


RUSTIC_TRADE_WINDOW_SPRITE = "src/ui/trade_window_rustic.png"


def visible_renderables(env: "Environment") -> list[tuple[int, Entity, Renderable]]:
    """Collect visible renderable entities sorted by their draw order."""
    renderables: list[tuple[int, Entity, Renderable]] = []
    for entity in env.state.entities:
        renderable = entity.get_component(Renderable)
        if renderable is not None and renderable.visible:
            renderables.append((renderable.z_index, entity, renderable))
    renderables.sort(key=lambda item: item[0])
    return renderables


def sidebar_is_allowed(env: "Environment") -> bool:
    """Allow the right HUD only for human-controlled input surfaces."""
    human_policy_names = {
        "Human_Takes_Action",
        "Human_Communication_Policy",
        "Human_Trading_Policy",
    }
    for entity in getattr(getattr(env, "state", None), "entities", []):
        for component in getattr(entity, "components", {}).values():
            if component.__class__.__name__ in human_policy_names:
                return True
    return False


def background_items(env: "Environment", renderer: "Pygame_Renderer") -> list[dict[str, Any]]:
    """Fetch and normalize background tiles from the active layout adapter."""
    return [normalize_background_item(item) for item in renderer.layout.background(env)]




def entity_health_value(entity: Entity) -> float | None:
    """Read an entity's health value from any health-like component."""
    for component in entity.components.values():
        if hasattr(component, "current_health"):
            return float(getattr(component, "current_health"))
        if hasattr(component, "health"):
            return float(getattr(component, "health"))
    return None


def entity_max_health_value(entity: Entity) -> float | None:
    """Read an entity's max-health value from any health-like component."""
    for component in entity.components.values():
        if hasattr(component, "max_health"):
            return float(getattr(component, "max_health"))
    return None



def title_case_name(raw: str) -> str:
    """Convert snake/camel-ish names into short label text."""
    return raw.replace("_", " ").strip().title()




def entity_inventory_entries(entity: Entity, env: "Environment" | None = None) -> list[dict[str, Any]]:
    """Return inventory entries with names, counts, and sprite hints for the inspector card."""
    sprite_map = dict(getattr(env, "inventory_sprite_map", {})) if env is not None else {}
    entries: list[dict[str, Any]] = []

    for component in entity.components.values():
        inventory = getattr(component, "contents", None) or getattr(component, "inventory", None)
        if isinstance(inventory, list):
            aggregated: dict[tuple[str, str | None], int] = {}
            for item in inventory:
                item_name = getattr(item, "name", str(item))
                item_renderable = item.get_component(Renderable) if hasattr(item, "get_component") else None
                sprite_name = None if item_renderable is None else item_renderable.sprite_path
                key = (item_name, sprite_name)
                aggregated[key] = aggregated.get(key, 0) + 1
            for (name, sprite_name), count in aggregated.items():
                entries.append({"name": name, "count": count, "sprite": sprite_name})
            if entries:
                return entries

        if isinstance(inventory, dict):
            for name, count in inventory.items():
                count_int = int(count)
                if count_int <= 0:
                    continue
                singular = str(name).rstrip("s")
                sprite_name = sprite_map.get(str(name)) or sprite_map.get(singular)
                entries.append({"name": title_case_name(str(name)), "count": count_int, "sprite": sprite_name})
            if entries:
                return entries

    return entries


def component_stat_pairs(entity: Entity) -> list[tuple[str, str]]:
    """Derive quantifiable status stats from the entity state."""
    stats: list[tuple[str, str]] = []

    health = entity_health_value(entity)
    max_health = entity_max_health_value(entity)
    if health is not None and max_health is not None:
        stats.append(("HP", f"{int(health)}/{int(max_health)}"))
    elif health is not None:
        stats.append(("HP", f"{int(health)}"))

    for component in entity.components.values():
        if hasattr(component, "money"):
            stats.append(("Money", str(int(getattr(component, "money")))))
            break

    return stats


def entity_primary_stats(entity: Entity, env: "Environment" | None = None) -> list[tuple[str, str]]:
    """Return compact key/value pairs for the floating entity card."""
    return component_stat_pairs(entity)[:4]


def selected_card_metrics(renderer: "Pygame_Renderer", *, stat_count: int, inventory_line_count: int) -> dict[str, int]:
    """Derive all selected-entity card sizing from a shared tile-based scale."""
    base = max(56, int(renderer.tile_size))
    outer_pad = max(10, int(base * 0.18))
    inner_gap = max(8, int(base * 0.14))
    portrait_size = max(56, int(base * 1.08))
    line_gap = max(2, int(base * 0.05))
    tail_height = max(12, int(base * 0.22))
    text_line_height = renderer.small_font.get_linesize() + line_gap
    stat_block_min_height = int(base * 0.9) + stat_count * text_line_height
    inventory_block_min_height = 0 if inventory_line_count <= 0 else inner_gap + (inventory_line_count + 1) * text_line_height
    info_height = max(portrait_size, stat_block_min_height + inventory_block_min_height)
    return {
        "base": base,
        "outer_pad": outer_pad,
        "inner_gap": inner_gap,
        "portrait_size": portrait_size,
        "line_gap": line_gap,
        "text_line_height": text_line_height,
        "tail_height": tail_height,
        "corner_radius": max(14, int(base * 0.22)),
        "info_height": info_height,
    }


def selected_entity(env: "Environment", renderer: "Pygame_Renderer") -> Entity | None:
    """Return the entity currently selected in the renderer, if it still exists."""
    selected_name = getattr(renderer, "selected_entity_name", None)
    if not selected_name:
        return None
    return next((entity for entity in env.state.entities if entity.name == selected_name), None)


def focused_entity(env: "Environment", renderer: "Pygame_Renderer") -> Entity | None:
    """Return the camera-focused agent if it is still present."""
    focus_name = getattr(renderer, "camera_focus_entity_name", None)
    if not focus_name:
        return None
    return next(
        (
            entity for entity in env.state.entities
            if entity.name == focus_name and getattr(entity, "is_agent", False)
        ),
        None,
    )


def update_damage_flash_state(renderer: "Pygame_Renderer", env: "Environment") -> None:
    """Track recent health drops so damaged entities can flash briefly."""
    now = time.monotonic()
    active_names = {entity.name for entity in env.state.entities}
    renderer._damage_flash_until = {
        name: until
        for name, until in renderer._damage_flash_until.items()
        if name in active_names and until > now
    }
    for entity_name in getattr(env, "hit_entity_names", []):
        if entity_name in active_names:
            renderer._damage_flash_until[entity_name] = max(
                renderer._damage_flash_until.get(entity_name, 0.0),
                now + 1.0,
            )

    next_health_values: dict[str, float] = {}
    for entity in env.state.entities:
        health_value = entity_health_value(entity)
        if health_value is None:
            continue
        next_health_values[entity.name] = health_value
        previous_value = renderer._last_health_values.get(entity.name)
        if previous_value is not None and health_value < previous_value:
            renderer._damage_flash_until[entity.name] = now + 1.0
            renderer.camera_shake_until = max(renderer.camera_shake_until, now + 0.22)
            renderer.camera_shake_strength = max(renderer.camera_shake_strength, renderer.tile_size * 0.12)

    renderer._last_health_values = next_health_values


def entity_world_position(renderer: "Pygame_Renderer", entity: Entity) -> tuple[int, int] | None:
    """Return an entity's tile position in renderer world coordinates."""
    position = getattr(entity, "position", None)
    if position is None:
        return None
    x, y = renderer.layout.screen_position(position)
    return int(x), int(y)


def update_camera_state(
    renderer: "Pygame_Renderer",
    env: "Environment",
    *,
    min_world_x: int,
    max_world_x: int,
    min_world_y: int,
    max_world_y: int,
) -> tuple[int, int, int, int]:
    """Choose visible tile bounds from either full-map or focused camera mode."""
    focus = focused_entity(env, renderer)
    if focus is None:
        renderer.camera_center = None
        renderer.camera_shake_strength = 0.0 if renderer.camera_shake_until <= time.monotonic() else renderer.camera_shake_strength
        return min_world_x, max_world_x, min_world_y, max_world_y

    renderer.camera_shake_strength = 0.0 if renderer.camera_shake_until <= time.monotonic() else renderer.camera_shake_strength
    world_position = entity_world_position(renderer, focus)
    if world_position is None:
        renderer.camera_center = None
        return min_world_x, max_world_x, min_world_y, max_world_y

    center_x, center_y = world_position
    radius = focus_radius(env, renderer)
    renderer.camera_focus_radius_tiles = radius
    renderer.camera_center = (center_x, center_y)
    return (
        max(min_world_x, center_x - radius),
        min(max_world_x, center_x + radius),
        max(min_world_y, center_y - radius),
        min(max_world_y, center_y + radius),
    )


def is_within_visible_bounds(x: int, y: int, min_x: int, max_x: int, min_y: int, max_y: int) -> bool:
    """Report whether a tile lies inside the active camera window."""
    return min_x <= x <= max_x and min_y <= y <= max_y


def visible_tile_set(env: "Environment", renderer: "Pygame_Renderer") -> set[tuple[int, int]] | None:
    """Return environment-level line-of-sight tiles when a focused agent is being inspected."""
    focus = focused_entity(env, renderer)
    if focus is None:
        return None
    visible_tiles_for = getattr(env, "visible_tiles_for", None)
    if callable(visible_tiles_for):
        return {tuple(tile) for tile in visible_tiles_for(renderer.camera_focus_entity_name)}
    visible_tiles = getattr(env, "visible_tiles", None)
    if callable(visible_tiles):
        return {tuple(tile) for tile in visible_tiles()}

    world_position = entity_world_position(renderer, focus)
    if world_position is None:
        return None
    center_x, center_y = world_position
    radius = focus_radius(env, renderer)
    return {
        (x, y)
        for x in range(center_x - radius, center_x + radius + 1)
        for y in range(center_y - radius, center_y + radius + 1)
    }


def flash_tinted_surface(image: Any, *, tint: tuple[int, int, int], alpha: int) -> Any:
    """Return a tinted copy of a sprite for temporary visual effects."""
    tinted = image.copy()
    overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
    overlay.fill((*tint, alpha))
    tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted


def animated_sprite_name(renderable: Renderable) -> str:
    """Choose the active sprite frame for a renderable."""
    frames = list(getattr(renderable, "animation_frames", []))
    if not frames:
        return renderable.sprite_path
    fps = max(0.01, float(getattr(renderable, "animation_fps", 5.0)))
    frame_index = int(time.monotonic() * fps) % len(frames)
    return frames[frame_index]


def interpolated_entity_screen_position(
    renderer: "Pygame_Renderer",
    entity: Entity,
    *,
    min_x: int,
    max_y: int,
    renderable: Renderable,
) -> tuple[int, int] | None:
    """Get entity screen position - NO interpolation, NO bobbing."""
    world_position = entity_world_position(renderer, entity)
    if world_position is None:
        return None

    # Direct position - no interpolation, no smoothing, no bobbing
    px, py = screen_rect_for_tile(renderer, world_position[0], world_position[1], min_x, max_y)
    return px, py


def draw_focus_ring(renderer: "Pygame_Renderer", entity: Entity, px: int, py: int) -> None:
    """Highlight the focused agent so the camera mode is visually obvious."""
    if renderer.camera_focus_entity_name != entity.name:
        return
    ring_rect = pygame.Rect(px - 4, py - 4, renderer.tile_size + 8, renderer.tile_size + 8)
    pygame.draw.rect(renderer.effect_surface, renderer.focus_outline_color, ring_rect, width=3, border_radius=10)


def draw_selection_ring(renderer: "Pygame_Renderer", entity: Entity, px: int, py: int) -> None:
    """Highlight the selected entity so inspection is visually anchored."""
    if getattr(renderer, "selected_entity_name", None) != entity.name:
        return
    ring_rect = pygame.Rect(px - 7, py - 7, renderer.tile_size + 14, renderer.tile_size + 14)
    glow = pygame.Surface((ring_rect.width + 12, ring_rect.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (*renderer.selection_outline_color, 58), glow.get_rect(), width=8, border_radius=16)
    renderer.effect_surface.blit(glow, (ring_rect.x - 6, ring_rect.y - 6))
    pygame.draw.rect(renderer.effect_surface, renderer.selection_outline_color, ring_rect, width=3, border_radius=12)


def draw_selected_entity_card(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    """Draw a floating inspector card above the selected entity."""
    inspected = selected_entity(env, renderer)
    if inspected is None:
        return

    position = entity_positions.get(inspected.name)
    if position is None:
        return

    px, py = position
    stats = entity_primary_stats(inspected, env)
    inventory_entries = entity_inventory_entries(inspected, env)
    title_font = renderer.hud_font
    body_font = renderer.small_font
    metrics = selected_card_metrics(renderer, stat_count=len(stats), inventory_line_count=min(4, len(inventory_entries)))
    name_surface = title_font.render(inspected.name, True, (244, 247, 252))
    subtitle = "Agent" if inspected.is_agent else "Entity"
    subtitle_surface = body_font.render(subtitle, True, (155, 205, 255))

    stat_surfaces = []
    label_color = (124, 182, 255)
    value_color = (220, 226, 235)
    for label, value in stats:
        stat_surfaces.append(
            (
                body_font.render(f"{label}:", True, label_color),
                body_font.render(str(value), True, value_color),
            )
        )
    inventory_header_surface = body_font.render("Inventory:", True, (232, 208, 164)) if inventory_entries else None
    inventory_item_surfaces = []
    for entry in inventory_entries[:4]:
        item_name = str(entry.get("name", "Item"))
        item_count = int(entry.get("count", 0))
        line = f"- {item_name} x{item_count}" if item_count > 1 else f"- {item_name}"
        inventory_item_surfaces.append(body_font.render(line, True, (189, 196, 206)))

    portrait_size = metrics["portrait_size"]
    line_gap = metrics["line_gap"]
    content_width = name_surface.get_width()
    content_width = max(content_width, subtitle_surface.get_width())
    for label_surface, value_surface in stat_surfaces:
        content_width = max(content_width, label_surface.get_width() + metrics["inner_gap"] + value_surface.get_width())
    if inventory_header_surface is not None:
        content_width = max(content_width, inventory_header_surface.get_width())
    for item_surface in inventory_item_surfaces:
        content_width = max(content_width, item_surface.get_width())

    top_info_width = portrait_size + metrics["inner_gap"] + content_width
    card_width = top_info_width + metrics["outer_pad"] * 2
    stats_height = (
        name_surface.get_height()
        + subtitle_surface.get_height()
        + metrics["inner_gap"]
        + len(stat_surfaces) * (body_font.get_linesize() + line_gap)
    )
    inventory_text_height = 0
    if inventory_header_surface is not None:
        inventory_text_height = metrics["inner_gap"] + inventory_header_surface.get_height()
        if inventory_item_surfaces:
            inventory_text_height += metrics["line_gap"] + len(inventory_item_surfaces) * metrics["text_line_height"]
    text_block_height = stats_height + inventory_text_height
    top_info_height = max(portrait_size, text_block_height)
    card_height = metrics["outer_pad"] * 2 + top_info_height
    tail_height = metrics["tail_height"]
    card_x = px + renderer.tile_size // 2 - card_width // 2
    card_y = py - card_height - tail_height - metrics["outer_pad"]

    world_width = renderer.effect_surface.get_width()
    world_height = renderer.effect_surface.get_height()
    card_x = max(10, min(card_x, world_width - card_width - 10))
    card_y = max(10, min(card_y, world_height - card_height - tail_height - 10))

    card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
    shadow_rect = card_rect.move(5, 6)
    shadow = pygame.Surface((shadow_rect.width, shadow_rect.height), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 92), shadow.get_rect(), border_radius=18)
    renderer.effect_surface.blit(shadow, shadow_rect.topleft)

    pygame.draw.rect(renderer.effect_surface, (24, 30, 42, 238), card_rect, border_radius=metrics["corner_radius"])
    pygame.draw.rect(
        renderer.effect_surface,
        renderer.selection_panel_accent,
        card_rect,
        width=2,
        border_radius=metrics["corner_radius"],
    )

    tail_anchor_x = px + renderer.tile_size // 2
    tail_anchor_x = max(card_rect.left + 24, min(tail_anchor_x, card_rect.right - 24))
    tail = [
        (tail_anchor_x - 12, card_rect.bottom - 2),
        (tail_anchor_x + 12, card_rect.bottom - 2),
        (px + renderer.tile_size // 2, py - 8),
    ]
    pygame.draw.polygon(renderer.effect_surface, (24, 30, 42, 238), tail)
    pygame.draw.polygon(renderer.effect_surface, renderer.selection_panel_accent, tail, width=2)

    portrait_rect = pygame.Rect(
        card_rect.x + metrics["outer_pad"],
        card_rect.y + metrics["outer_pad"],
        portrait_size,
        portrait_size,
    )
    pygame.draw.rect(renderer.effect_surface, (39, 48, 66), portrait_rect, border_radius=14)
    pygame.draw.rect(renderer.effect_surface, (86, 101, 132), portrait_rect, width=1, border_radius=14)

    sprite_name = None
    renderable = inspected.get_component(Renderable)
    if renderable is not None:
        sprite_name = animated_sprite_name(renderable)
    if sprite_name:
        portrait_image = get_scaled_image(renderer, sprite_name, portrait_size - 10, portrait_size - 10)
        if portrait_image is not None:
            image_x = portrait_rect.x + (portrait_rect.width - portrait_image.get_width()) // 2
            image_y = portrait_rect.y + (portrait_rect.height - portrait_image.get_height()) // 2
            renderer.effect_surface.blit(portrait_image, (image_x, image_y))

    text_left = portrait_rect.right + metrics["inner_gap"]
    text_y = card_rect.y + metrics["outer_pad"] - 2
    renderer.effect_surface.blit(name_surface, (text_left, text_y))
    text_y += name_surface.get_height() + 2
    renderer.effect_surface.blit(subtitle_surface, (text_left, text_y))
    text_y += subtitle_surface.get_height() + metrics["inner_gap"]

    for label_surface, value_surface in stat_surfaces:
        renderer.effect_surface.blit(label_surface, (text_left, text_y))
        renderer.effect_surface.blit(value_surface, (text_left + label_surface.get_width() + metrics["inner_gap"], text_y))
        text_y += metrics["text_line_height"]

    if inventory_header_surface is not None:
        text_y += max(2, metrics["line_gap"])
        renderer.effect_surface.blit(inventory_header_surface, (text_left, text_y))
        text_y += metrics["text_line_height"]
        for item_surface in inventory_item_surfaces:
            renderer.effect_surface.blit(item_surface, (text_left, text_y))
            text_y += metrics["text_line_height"]


def draw_emissive_glow(renderer: "Pygame_Renderer", sprite_name: str, px: int, py: int, intensity: int) -> None:
    """Add a soft glow behind emissive sprites and props."""
    glow_size = int(renderer.tile_size * 1.5)
    glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
    pygame.draw.ellipse(glow, (255, 220, 140, max(18, min(180, intensity))), glow.get_rect())
    glow_x = px + (renderer.tile_size - glow_size) // 2
    glow_y = py + (renderer.tile_size - glow_size) // 2
    renderer.light_surface.blit(glow, (glow_x, glow_y), special_flags=pygame.BLEND_RGBA_ADD)
    emissive_image = get_scaled_image(renderer, sprite_name, renderer.tile_size, renderer.tile_size)
    if emissive_image is not None:
        renderer.light_surface.blit(emissive_image, (px, py), special_flags=pygame.BLEND_RGBA_ADD)


def blit_scaled_sprite(
    renderer: "Pygame_Renderer",
    sprite_name: str,
    px: int,
    py: int,
    *,
    width: int,
    height: int,
    anchor: str = "center",
    missing_ok: bool = False,
) -> bool:
    """Load, scale, and draw a sprite at a tile with the chosen anchor."""
    image = get_scaled_image(renderer, sprite_name, width, height)
    if image is None:
        if missing_ok:
            return False
        raise FileNotFoundError(f"Sprite could not be resolved: '{sprite_name}'.")

    if anchor == "top_right":
        draw_x = px + renderer.tile_size - width
        draw_y = py
    elif anchor == "top_left":
        draw_x = px
        draw_y = py
    else:
        draw_x = px + (renderer.tile_size - width) // 2
        draw_y = py + (renderer.tile_size - height) // 2

    renderer.world_surface.blit(image, (draw_x, draw_y))
    return True


def draw_wall_sprite(renderer: "Pygame_Renderer", wall_set: str, px: int, py: int, neighbors: dict[str, bool]) -> bool:
    """Draw a wall tile using the best matching sprite variant."""
    sprite_name = resolve_wall_sprite(renderer, wall_set, neighbors)
    if sprite_name is None:
        raise FileNotFoundError(f"Wall set '{wall_set}' has no matching sprite variant for neighbors {neighbors}.")
    blit_scaled_sprite(
        renderer,
        sprite_name,
        px,
        py,
        width=renderer.tile_size,
        height=renderer.tile_size,
        anchor="top_left",
    )
    return True


def draw_wall_background_tile(
    renderer: "Pygame_Renderer",
    item: dict[str, Any],
    px: int,
    py: int,
    *,
    wall_positions: set[tuple[int, int]],
) -> bool:
    """Draw a wall background tile from its sprite set."""
    if item.get("kind") != "wall":
        return False

    wall_set = item.get("wall_set")
    if not wall_set:
        raise ValueError(f"Wall background tile is missing 'wall_set': {item!r}")

    neighbors = wall_neighbor_mask(int(item["x"]), int(item["y"]), wall_positions)
    return draw_wall_sprite(renderer, str(wall_set), px, py, neighbors)




def draw_entity_items(
    renderer: "Pygame_Renderer",
    items: list[Entity],
    px: int,
    py: int,
    *,
    layout_mode: str = "grid",  # "grid", "badges", "center", "corner"
    max_items: int = 4,
    scale: float = 0.45,
    
) -> None:
    """Draw items as overlays on an entity using flexible layouts.

    Args:
        layout_mode: How to position items:
            - "grid": 2x2 centered grid (for containers)
            - "badges": Top-right and bottom-left corners (for inventory)
            - "center": Single centered item (for holders, crafter output)
            - "corner": Top-right corner only (for crafter input)
        max_items: Maximum items to display (1-4)
        scale: Size as fraction of tile_size
        fallback_colors: Colors for fallback squares per item
    """
    if not items or max_items <= 0:
        return

    tile_s = renderer.tile_size

    # Calculate item size
    if layout_mode == "center":
        item_size = max(20, int(tile_s * 0.55))
    elif layout_mode == "badges":
        item_size = max(14, int(tile_s * scale))
    else:
        item_size = max(16, int(tile_s * scale))

    # Define positions based on layout
    if layout_mode == "grid":
        gap = max(2, int(tile_s * 0.05))
        total = 2 * item_size + gap
        start_x = px + (tile_s - total) // 2
        start_y = py + (tile_s - total) // 2
        positions = [
            (start_x, start_y),  # top-left
            (start_x + item_size + gap, start_y),  # top-right
            (start_x, start_y + item_size + gap),  # bottom-left
            (start_x + item_size + gap, start_y + item_size + gap),  # bottom-right
        ]
    elif layout_mode == "badges":
        positions = [
            (px + tile_s - item_size - 2, py + 2),  # top-right
            (px + 2, py + tile_s - item_size - 2),  # bottom-left
        ]
    elif layout_mode == "center":
        positions = [(px + (tile_s - item_size) // 2, py + (tile_s - item_size) // 2)]
    elif layout_mode == "corner":
        positions = [(px + tile_s - item_size - 2, py + 2)]  # top-right
    else:
        positions = [(px, py)]  # fallback

    # Draw each item
    for idx, item in enumerate(items[:max_items]):
        if idx >= len(positions):
            break
        draw_x, draw_y = positions[idx]

        renderable = item.get_component(Renderable)
        if renderable is None or not renderable.sprite_path:
            continue

        image = get_scaled_image(renderer, renderable.sprite_path, item_size, item_size)
        if image is not None:
            renderer.effect_surface.blit(image, (draw_x, draw_y))

    # Draw ellipsis if more items exist (grid mode only)
    if layout_mode == "grid" and len(items) > max_items:
        gap = max(2, int(tile_s * 0.05))
        total = 2 * item_size + gap
        ellipsis_x = px + (tile_s + total) // 2 + gap
        ellipsis_y = py + (tile_s + total) // 2 - item_size // 2
        surface = renderer.small_font.render("...", True, (200, 200, 200))
        renderer.effect_surface.blit(surface, (ellipsis_x, ellipsis_y))


# Deprecated: use draw_entity_items() instead
def draw_entity(renderer: "Pygame_Renderer", entity: Entity, renderable: Renderable, px: int, py: int) -> None:
    """Draw an entity sprite, including damage flash and optional overlay."""
    sprite_name = animated_sprite_name(renderable)
    image = get_or_load_image(renderer, sprite_name)
    if image is None:
        raise FileNotFoundError(
            f"Sprite renderer expected a valid sprite path for '{entity.name}', but could not resolve '{sprite_name}'."
        )
    scaled_image = get_scaled_image(renderer, sprite_name, renderer.tile_size, renderer.tile_size)
    if scaled_image is None:
        raise FileNotFoundError(
            f"Sprite renderer expected a valid sprite path for '{entity.name}', but could not resolve '{sprite_name}'."
        )
    flash_until = renderer._damage_flash_until.get(entity.name, 0.0)
    if flash_until > time.monotonic():
        scaled_image = flash_tinted_surface(scaled_image, tint=(190, 20, 20), alpha=140)
    shadow_scale = max(0.2, float(getattr(renderable, "shadow_scale", 0.72)))
    is_wall = renderable.wall_set is not None
    if not is_wall:
        shadow_width = max(14, int(renderer.tile_size * shadow_scale))
        shadow_height = max(8, int(renderer.tile_size * max(0.18, shadow_scale * 0.32)))
        shadow = pygame.Surface((shadow_width, shadow_height), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 72), shadow.get_rect())
        shadow_x = px + (renderer.tile_size - shadow_width) // 2
        shadow_y = py + renderer.tile_size - shadow_height // 2 - max(2, renderer.tile_size // 12)
        renderer.shadow_surface.blit(shadow, (shadow_x, shadow_y))
    renderer.entity_surface.blit(scaled_image, (px, py))
    renderer._last_drawn_entity_rects[entity.name] = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
    draw_selection_ring(renderer, entity, px, py)
    draw_focus_ring(renderer, entity, px, py)

    if renderable.overlay_sprite:
        mode = getattr(renderable, "overlay_mode", "badge")
        scale = getattr(renderable, "overlay_scale", None)
        if mode == "full":
            overlay_size = renderer.tile_size
            anchor = "top_left"
        elif mode == "center":
            ratio = scale if scale is not None else 0.72
            overlay_size = max(20, int(renderer.tile_size * ratio))
            anchor = "center"
        else:
            ratio = scale if scale is not None else 0.32
            overlay_size = max(14, int(renderer.tile_size * ratio))
            anchor = "top_right"
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.effect_surface
        try:
            blit_scaled_sprite(renderer, renderable.overlay_sprite, px, py, width=overlay_size, height=overlay_size, anchor=anchor)
        finally:
            renderer.world_surface = previous_world_surface

    container = entity.get_component(Container)
    if container is not None and container.is_open:
        visible = container.visible_contents()[:4] if hasattr(container, "visible_contents") else []
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.effect_surface
        try:
            draw_entity_items(renderer, visible, px, py, layout_mode="grid", max_items=4)
        finally:
            renderer.world_surface = previous_world_surface

    # Inventory overlay
    inventory = entity.get_component(Inventory)
    if inventory is not None:
        inv_list = getattr(inventory, 'contents', [])
        if len(inv_list) > 0 and not getattr(renderable, 'overlay_sprite', None):
            items = inv_list[:2]
            draw_entity_items(renderer, items, px, py, layout_mode="badges", max_items=2, scale=0.50)

    crafter = entity.get_component(Crafter)
    if crafter is not None:
        has_inputs = len(crafter.staged_items) > 0
        has_output = crafter.output_item is not None
        output_already_drawn = has_output and getattr(renderable, 'overlay_sprite', None)
        if has_inputs or has_output:
            if crafter.staged_items:
                draw_entity_items(renderer, [crafter.staged_items[0]], px, py, layout_mode="corner", max_items=1, scale=0.42)
            if not output_already_drawn:
                output = getattr(crafter, "output_item", None)
                if output:
                    draw_entity_items(renderer, [output], px, py, layout_mode="center", max_items=1, scale=0.55)

    holder = entity.get_component(Single_Item_Holder)
    if holder is not None:
        stored = getattr(holder, 'stored_item', None)
        if stored:
            draw_entity_items(renderer, [stored], px, py, layout_mode="center", max_items=1, scale=0.55)

    emissive_sprite = getattr(renderable, "emissive_sprite", None)
    if emissive_sprite:
        draw_emissive_glow(renderer, emissive_sprite, px, py, int(getattr(renderable, "emissive_intensity", 84)))

    foreground_sprite = getattr(renderable, "foreground_sprite", None)
    if foreground_sprite:
        ratio = float(getattr(renderable, "foreground_scale", 1.0) or 1.0)
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.foreground_surface
        try:
            blit_scaled_sprite(
                renderer,
                foreground_sprite,
                px,
                py,
                width=max(16, int(renderer.tile_size * ratio)),
                height=max(16, int(renderer.tile_size * ratio)),
                anchor="top_left",
                missing_ok=True,
            )
        finally:
            renderer.world_surface = previous_world_surface


def draw_hit_effects(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    """Draw transient hit-effect sprites centered on affected entities."""
    hit_effects = list(getattr(env, "hit_effects", []))
    if not hit_effects:
        return

    for effect in hit_effects:
        entity_name = effect.get("entity_name")
        sprite_name = effect.get("sprite")
        if not entity_name or not sprite_name or entity_name not in entity_positions:
            continue

        px, py = entity_positions[entity_name]
        ratio = float(effect.get("scale", 0.75))
        effect_size = max(20, int(renderer.tile_size * ratio))
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.effect_surface
        try:
            blit_scaled_sprite(
                renderer,
                str(sprite_name),
                px,
                py,
                width=effect_size,
                height=effect_size,
                anchor="center",
                missing_ok=True,
            )
        finally:
            renderer.world_surface = previous_world_surface

        for particle_index in range(6):
            offset_x = int(math.cos((particle_index / 6) * math.tau + time.monotonic() * 4.0) * renderer.tile_size * 0.18)
            offset_y = int(math.sin((particle_index / 6) * math.tau + time.monotonic() * 4.0) * renderer.tile_size * 0.18)
            particle_rect = pygame.Rect(
                px + renderer.tile_size // 2 + offset_x - 2,
                py + renderer.tile_size // 2 + offset_y - 2,
                4,
                4,
            )
            pygame.draw.ellipse(renderer.effect_surface, (255, 226, 158, 140), particle_rect)


def draw_background_tile(
    renderer: "Pygame_Renderer",
    item: dict[str, Any],
    px: int,
    py: int,
    *,
    wall_positions: set[tuple[int, int]],
) -> None:
    """Draw one background tile and require explicit sprite-backed assets."""
    kind = item.get("kind", "floor")
    if draw_wall_background_tile(renderer, item, px, py, wall_positions=wall_positions):
        return

    sprite_name = item.get("sprite")
    if not sprite_name:
        raise ValueError(f"Background tile kind '{kind}' is missing required 'sprite': {item!r}")

    image = get_scaled_image(renderer, sprite_name, renderer.tile_size, renderer.tile_size)
    if image is None:
        rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
        pygame.draw.rect(renderer.floor_surface, (40, 50, 60), rect)
        pygame.draw.rect(renderer.floor_surface, (60, 70, 80), rect, 1)
        return

    # Draw the image
    renderer.floor_surface.blit(image, (px, py))



def draw_grid_overlay(renderer: "Pygame_Renderer", min_x: int, max_x: int, min_y: int, max_y: int) -> None:
    """Draw grid lines over the world area for debugging or readability."""
    overlay_color = (30, 30, 34)
    for x in range(min_x, max_x + 2):
        px = renderer.margin + (x - min_x) * renderer.tile_size
        pygame.draw.line(
            renderer.world_surface,
            overlay_color,
            (px, renderer.margin),
            (px, renderer.margin + (max_y - min_y + 1) * renderer.tile_size),
            2,
        )


def draw_visibility_mask(
    renderer: "Pygame_Renderer",
    visible_tiles: set[tuple[int, int]] | None,
    min_x: int,
    max_y: int,
) -> None:
    """Darken tiles outside the active sight radius to visualize limited perception."""
    if not visible_tiles:
        return
    fog_tile = get_scaled_image(renderer, "effects/fog.png", renderer.tile_size, renderer.tile_size)
    world_width = renderer.floor_surface.get_width()
    world_height = renderer.floor_surface.get_height()
    tiles_x = max(0, (world_width - renderer.viewport_pad_w - renderer.viewport_pad_e) // renderer.tile_size)
    tiles_y = max(0, (world_height - renderer.viewport_pad_n - renderer.viewport_pad_s) // renderer.tile_size)
    for row in range(tiles_y):
        for col in range(tiles_x):
            world_x = min_x + col
            world_y = max_y - row
            rect = pygame.Rect(
                renderer.viewport_pad_w + col * renderer.tile_size,
                renderer.viewport_pad_n + row * renderer.tile_size,
                renderer.tile_size,
                renderer.tile_size,
            )
            if (world_x, world_y) not in visible_tiles:
                if fog_tile is not None:
                    renderer.effect_surface.blit(fog_tile, rect.topleft)
                veil = pygame.Surface((renderer.tile_size, renderer.tile_size), pygame.SRCALPHA)
                veil.fill((8, 10, 14, 152))
                renderer.effect_surface.blit(veil, rect.topleft)


def draw_hud_panel(renderer: "Pygame_Renderer", env: "Environment", x_offset: int, width: int, height: int) -> None:
    """Render the bottom HUD panel with step counter, mode, and controls."""
    if getattr(env, "hide_bottom_hud", False):
        return

    hud_top = height - renderer.hud_height
    panel_rect = pygame.Rect(x_offset, hud_top, width, renderer.hud_height)
    pygame.draw.rect(renderer.screen, (14, 17, 24), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, hud_top), (x_offset + width, hud_top), 2)

    # Step counter and mode
    tick = getattr(env, "tick", getattr(env, "cur_step", 0))
    episode_length = getattr(env, "episode_length", None)
    current_phase = getattr(env, "current_phase", None)

    if current_phase is not None:
        header_text = f"Step: {tick}" + (f" / {episode_length}" if episode_length else "") + f" | Mode: {current_phase}"
    else:
        score = getattr(env, "score", 0)
        header_text = f"Tick {tick} Score {score}"

    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (x_offset + renderer.margin, hud_top + 16))

    # Controls hint - minimal
    controls_text = "Click agent: follow | click empty: full | R: reset | ESC: exit"
    controls = renderer.small_font.render(controls_text, True, (150, 160, 180))
    renderer.screen.blit(controls, (x_offset + renderer.margin, hud_top + 48))

def draw_sidebar_panel(renderer: "Pygame_Renderer", env: "Environment", world_width: int, height: int, sidebar_width: int) -> None:
    """Render an optional right-hand sidebar with agent observations and options."""
    if sidebar_width <= 0:
        return

    panel_rect = pygame.Rect(world_width, 0, sidebar_width, height)
    pygame.draw.rect(renderer.screen, (12, 15, 21), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (world_width, 0), (world_width, height), 2)

    header_text = getattr(env, "hud_sidebar_header", "Agent View")
    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (world_width + 16, 14))

    sidebar_lines = list(getattr(env, "hud_sidebar_lines", []))
    selected_action_lines = list(getattr(env, "hud_sidebar_selected_action", []))
    action_lines = list(getattr(env, "hud_sidebar_actions", []))
    y = 48
    line_height = renderer.small_font.get_linesize() + 4
    max_width = sidebar_width - 32
    wrapped_selected_action_lines: list[str] = []
    wrapped_action_lines: list[str] = []
    if selected_action_lines:
        for message in selected_action_lines:
            wrapped = wrap_text_lines(renderer.small_font, str(message), max_width=max_width)
            wrapped_selected_action_lines.extend(wrapped[:3])
    if action_lines:
        for message in action_lines:
            wrapped = wrap_text_lines(renderer.small_font, str(message), max_width=max_width)
            wrapped_action_lines.extend(wrapped[:3])
    action_block_height = 0
    if wrapped_action_lines:
        action_block_height = 12 + len(wrapped_action_lines) * line_height

    top_limit = max(y, height - 26 - action_block_height)
    for message in sidebar_lines[:24]:
        wrapped = wrap_text_lines(renderer.small_font, str(message), max_width=max_width)
        for wrapped_line in wrapped[:3]:
            if y > top_limit:
                break
            surface = renderer.small_font.render(wrapped_line, True, (189, 196, 206))
            renderer.screen.blit(surface, (world_width + 16, y))
            y += line_height
        if y > top_limit:
            break
        y += 4

    action_y = height - 18 - len(wrapped_action_lines) * line_height
    chosen_height = len(wrapped_selected_action_lines) * line_height
    chosen_y = max(y + 8, action_y - chosen_height - (8 if wrapped_selected_action_lines and wrapped_action_lines else 0))
    if wrapped_selected_action_lines:
        for wrapped_line in wrapped_selected_action_lines:
            if chosen_y > height - 26:
                break
            color = (235, 213, 154) if wrapped_line == "Chosen Action:" else (189, 196, 206)
            surface = renderer.small_font.render(wrapped_line, True, color)
            renderer.screen.blit(surface, (world_width + 16, chosen_y))
            chosen_y += line_height

    if wrapped_action_lines:
        for wrapped_line in wrapped_action_lines:
            if action_y > height - 26:
                break
            color = (235, 213, 154) if wrapped_line == "Possible Actions:" else (189, 196, 206)
            surface = renderer.small_font.render(wrapped_line, True, color)
            renderer.screen.blit(surface, (world_width + 16, action_y))
            action_y += line_height


def draw_end_overlay(renderer: "Pygame_Renderer", env: "Environment", world_x: int, world_width: int, world_height: int) -> None:
    """Draw a centered overlay when the environment reaches a terminal state."""
    terminations = list(getattr(env, "terminations", []))
    truncations = list(getattr(env, "truncations", []))
    final_boss_defeated = bool(getattr(env, "final_boss_defeated", False))
    experiment_completed = bool(getattr(env, "experiment_completed", False))
    if not final_boss_defeated and not experiment_completed:
        return

    if final_boss_defeated:
        title = "Raid Complete"
        subtitle = "The Ash Warden has fallen."
        accent = (206, 182, 92)
    else:
        title = "Experiment Completed"
        subtitle = str(
            getattr(
                env,
                "completion_subtitle",
                "The scheduled run has finished.",
            )
        )
        accent = (149, 161, 178)

    overlay = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    overlay.fill((8, 10, 16, 170))
    renderer.screen.blit(overlay, (world_x, 0))

    # Calculate text dimensions with wrapping support
    title_surface = renderer.font.render(title, True, (245, 247, 250))

    # Wrap subtitle text to fit within max width
    max_text_width = min(480, world_width - 80)
    subtitle_lines = wrap_text_lines(renderer.hud_font, subtitle, max_width=max_text_width)
    subtitle_surfaces = [renderer.hud_font.render(line, True, accent) for line in subtitle_lines]
    subtitle_height = sum(surf.get_height() for surf in subtitle_surfaces)
    subtitle_width = max((surf.get_width() for surf in subtitle_surfaces), default=0)

    # Calculate box size to fit text with padding
    pad_x = 40
    pad_y = 24
    line_spacing = 12
    content_width = max(title_surface.get_width(), subtitle_width)
    content_height = title_surface.get_height() + line_spacing + subtitle_height
    box_width = min(max(320, content_width + pad_x * 2), world_width - 40)
    box_height = max(120, content_height + pad_y * 2 + 20)
    box_x = (world_width - box_width) // 2
    box_y = (world_height - box_height) // 2
    panel_rect = pygame.Rect(world_x + box_x, box_y, box_width, box_height)
    pygame.draw.rect(renderer.screen, (18, 22, 30), panel_rect, border_radius=18)
    pygame.draw.rect(renderer.screen, accent, panel_rect, width=3, border_radius=18)

    # Draw title centered
    title_x = world_x + box_x + (box_width - title_surface.get_width()) // 2
    renderer.screen.blit(title_surface, (title_x, box_y + pad_y))

    # Draw wrapped subtitle lines centered
    subtitle_y = box_y + pad_y + title_surface.get_height() + line_spacing
    for surf in subtitle_surfaces:
        subtitle_x = world_x + box_x + (box_width - surf.get_width()) // 2
        renderer.screen.blit(surf, (subtitle_x, subtitle_y))
        subtitle_y += surf.get_height() + 2


def draw_world_vignette(renderer: "Pygame_Renderer", world_x: int, world_width: int, world_height: int) -> None:
    """Apply a subtle darkening toward the edges of the world view."""
    cache_key = (world_width, world_height)
    overlay = renderer._vignette_cache.get(cache_key)
    if overlay is None:
        overlay = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
        center_x = world_width / 2
        center_y = world_height / 2
        max_distance = math.hypot(center_x, center_y) or 1.0
        for y in range(world_height):
            for x in range(world_width):
                distance = math.hypot(x - center_x, y - center_y)
                alpha = int(max(0.0, min(78.0, ((distance / max_distance) ** 1.9) * 78.0)))
                overlay.set_at((x, y), (6, 8, 12, alpha))
        renderer._vignette_cache[cache_key] = overlay
    renderer.screen.blit(overlay, (world_x, 0))


def wrap_text_lines(font: Any, text: str, max_width: int) -> list[str]:
    """Wrap text greedily into lines that fit within the given width."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_wrapped_text_lines(
    fonts: list[Any],
    text: str,
    *,
    max_width: int,
    max_lines: int,
) -> tuple[Any, list[str]]:
    """Choose a font and wrapped lines that fit within the speech-bubble limits."""
    for font in fonts:
        lines = wrap_text_lines(font, text, max_width=max_width)
        if len(lines) <= max_lines:
            return font, lines
    fallback_font = fonts[-1]
    lines = wrap_text_lines(fallback_font, text, max_width=max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last_line = lines[-1]
        while last_line and fallback_font.size(f"{last_line}...")[0] > max_width:
            last_line = last_line[:-1].rstrip()
        lines[-1] = f"{last_line}..." if last_line else "..."
    return fallback_font, lines


def collect_speech_bubbles(env: "Environment") -> list[dict[str, Any]]:
    """Collect renderer-owned speech bubble events.

    Renderer hooks publish normal chat into env.speech_bubbles. The
    Renderable.last_message scan is kept as a legacy fallback for older
    examples and replay/discussion helpers.
    """
    bubbles = list(getattr(env, "speech_bubbles", []))
    if bubbles:
        current_step = getattr(env, "cur_step", 0)
        visible_bubbles = []
        for bubble in bubbles:
            if not isinstance(bubble, dict) or "_step" not in bubble:
                visible_bubbles.append(bubble)
                continue
            ttl = int(bubble.get("ttl", 1))
            if current_step <= int(bubble["_step"]) + ttl:
                visible_bubbles.append(bubble)
        if hasattr(env, "__dict__"):
            env.speech_bubbles = visible_bubbles
        return visible_bubbles

    # Auto-collect from Renderable components
    for entity in getattr(env, "state", None).entities if hasattr(env, "state") else []:
        renderable = entity.get_component(Renderable)
        if renderable and renderable.last_message:
            bubbles.append({
                "entity_name": entity.name,
                "text": str(renderable.last_message),
            })

    return bubbles


def parse_trade_message(text: str) -> dict[str, Any] | None:
    """Parse compact renderer trade-message formats."""
    if not text.startswith("TRADE_SESSION:|"):
        return None
    try:
        parts = text.split("|")
        result: dict[str, Any] = {"_format": "session"}
        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                result[key] = value
        return result
    except Exception:
        return None


def _trade_items_from_field(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip() and item.strip() != "none"]


def _clamp_rect_to_surface(rect: pygame.Rect, surface: pygame.Surface, margin: int) -> pygame.Rect:
    x = max(margin, min(rect.x, surface.get_width() - rect.width - margin))
    y = max(margin, min(rect.y, surface.get_height() - rect.height - margin))
    return pygame.Rect(x, y, rect.width, rect.height)


def _trade_session_rect(
    renderer: "Pygame_Renderer",
    left_position: tuple[int, int],
    right_position: tuple[int, int],
    width: int,
    height: int,
) -> pygame.Rect:
    tile_s = renderer.tile_size
    margin = max(6, int(tile_s * 0.12))
    left_center = (left_position[0] + tile_s // 2, left_position[1] + tile_s // 2)
    right_center = (right_position[0] + tile_s // 2, right_position[1] + tile_s // 2)
    mid_x = (left_center[0] + right_center[0]) // 2
    mid_y = (left_center[1] + right_center[1]) // 2

    desired = pygame.Rect(mid_x - width // 2, mid_y - height // 2, width, height)
    return _clamp_rect_to_surface(desired, renderer.effect_surface, margin)


def _chat_session_rect(
    renderer: "Pygame_Renderer",
    participant_positions: list[tuple[int, int]],
    width: int,
    height: int,
) -> pygame.Rect:
    tile_s = renderer.tile_size
    margin = max(6, int(tile_s * 0.12))
    centers = [(x + tile_s // 2, y + tile_s // 2) for x, y in participant_positions]
    mid_x = sum(x for x, _ in centers) // len(centers)
    mid_y = sum(y for _, y in centers) // len(centers)
    desired = pygame.Rect(mid_x - width // 2, mid_y - height // 2, width, height)
    return _clamp_rect_to_surface(desired, renderer.effect_surface, margin)


def _chat_message_text(message: Any) -> str:
    text = str(message).strip()
    if text.startswith("Round ") and " - " in text:
        text = text.split(" - ", 1)[1]
    return text


def _ellipsize_text(font: Any, text: str, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text
    trimmed = text
    while trimmed and font.size(f"{trimmed}...")[0] > max_width:
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed}..." if trimmed else "..."


def draw_chat_session_window(
    renderer: "Pygame_Renderer",
    participant_positions: list[tuple[int, int]],
    participant_names: list[str],
    messages: list[Any],
    scale: float,
) -> None:
    if not participant_positions:
        return

    tile_s = renderer.tile_size
    surface_w = renderer.effect_surface.get_width()
    margin = max(8, int(tile_s * 0.14))
    panel_width = min(max(int(tile_s * 3.25 * scale), 190), max(96, surface_w - margin * 2))
    pad_x = max(8, int(tile_s * 0.13 * scale))
    pad_y = max(7, int(tile_s * 0.11 * scale))
    title_font = pygame.font.SysFont(None, max(13, int(tile_s * 0.20)), bold=True)
    body_font = pygame.font.SysFont(None, max(12, int(tile_s * 0.18)))
    line_gap = max(2, int(tile_s * 0.04))
    max_text_width = panel_width - pad_x * 2

    title = "Private: " + ", ".join(participant_names)
    visible_messages = [_chat_message_text(message) for message in messages[-4:]]
    wrapped_messages = []
    for message in visible_messages:
        wrapped_messages.append(wrap_text_lines(body_font, message, max_width=max_text_width)[:2])

    title_h = title_font.get_height()
    body_h = sum(len(lines) * body_font.get_height() for lines in wrapped_messages)
    gap_h = max(0, len(wrapped_messages) - 1) * line_gap
    panel_height = max(int(tile_s * 1.10 * scale), pad_y * 2 + title_h + line_gap + body_h + gap_h)
    panel_rect = _chat_session_rect(renderer, participant_positions, panel_width, panel_height)

    surface = renderer.effect_surface
    pygame.draw.rect(surface, (245, 239, 224), panel_rect, border_radius=max(8, int(tile_s * 0.15)))
    pygame.draw.rect(surface, (67, 55, 45), panel_rect, width=2, border_radius=max(8, int(tile_s * 0.15)))
    title_rect = pygame.Rect(panel_rect.left, panel_rect.top, panel_rect.width, pad_y + title_h + 3)
    pygame.draw.rect(surface, (82, 64, 49), title_rect, border_radius=max(8, int(tile_s * 0.15)))
    title_surface = title_font.render(title, True, (255, 238, 190))
    surface.blit(
        title_surface,
        (
            panel_rect.centerx - title_surface.get_width() // 2,
            panel_rect.top + max(3, pad_y // 2),
        ),
    )

    text_y = title_rect.bottom + line_gap
    for lines in wrapped_messages:
        for line in lines:
            text_surface = body_font.render(line, True, (30, 25, 22))
            surface.blit(text_surface, (panel_rect.left + pad_x, text_y))
            text_y += body_font.get_height()
        text_y += line_gap


def _draw_trade_currency(renderer: "Pygame_Renderer", x: int, y: int, amount: str, font: Any) -> None:
    if not amount:
        return
    radius = max(6, int(renderer.tile_size * 0.12))
    center = (x + radius, y + radius)
    pygame.draw.circle(renderer.effect_surface, (111, 70, 20), center, radius)
    pygame.draw.circle(renderer.effect_surface, (241, 188, 68), center, max(2, radius - 2))
    pygame.draw.circle(renderer.effect_surface, (255, 230, 132), (center[0] - radius // 3, center[1] - radius // 3), max(1, radius // 4))
    label = font.render(f"{amount}g", True, (72, 40, 18))
    renderer.effect_surface.blit(label, (x + radius * 2 + 3, y + radius - label.get_height() // 2))


def _trade_currency_width(renderer: "Pygame_Renderer", amount: str, font: Any) -> int:
    if not amount:
        return 0
    radius = max(6, int(renderer.tile_size * 0.12))
    return radius * 2 + 3 + font.size(f"{amount}g")[0]


def _fit_trade_item_sprite(sprite: pygame.Surface, max_size: int) -> pygame.Surface:
    visible_rect = sprite.get_bounding_rect()
    if visible_rect.width <= 0 or visible_rect.height <= 0:
        visible_rect = sprite.get_rect()
    cropped = sprite.subsurface(visible_rect)
    scale_factor = max_size / max(visible_rect.width, visible_rect.height)
    target_size = (
        max(1, int(round(visible_rect.width * scale_factor))),
        max(1, int(round(visible_rect.height * scale_factor))),
    )
    return pygame.transform.scale(cropped, target_size)


def _draw_trade_offer_grid(
    renderer: "Pygame_Renderer",
    rect: pygame.Rect,
    items: list[str],
    entity_lookup: dict[str, Entity],
    font: Any,
    text_color: tuple[int, int, int],
) -> None:
    surface = renderer.effect_surface
    pygame.draw.rect(surface, (47, 31, 21), rect)
    pygame.draw.rect(surface, (83, 55, 31), rect.inflate(-2, -2))
    pygame.draw.rect(surface, (32, 21, 15), rect, width=2)

    cell_size = rect.width // 2
    grid_color = (173, 113, 52)
    pygame.draw.line(surface, grid_color, (rect.left + cell_size, rect.top), (rect.left + cell_size, rect.bottom), width=2)
    pygame.draw.line(surface, grid_color, (rect.left, rect.top + cell_size), (rect.right, rect.top + cell_size), width=2)

    visible_items = items[:4]
    if len(items) > 4:
        visible_items = items[:3] + ["..."]

    for idx, item_name in enumerate(visible_items):
        col = idx % 2
        row = idx // 2
        cell_rect = pygame.Rect(rect.left + col * cell_size, rect.top + row * cell_size, cell_size, cell_size)
        inset = max(4, cell_size // 8)
        content_rect = cell_rect.inflate(-inset * 2, -inset * 2)

        if item_name == "...":
            ellipsis_font = pygame.font.SysFont(None, max(18, int(renderer.tile_size * 0.30)), bold=True)
            shadow = ellipsis_font.render("...", True, (26, 17, 11))
            ellipsis = ellipsis_font.render("...", True, text_color)
            surface.blit(
                shadow,
                (
                    cell_rect.centerx - shadow.get_width() // 2 + 1,
                    cell_rect.centery - shadow.get_height() // 2 + 1,
                ),
            )
            surface.blit(
                ellipsis,
                (
                    cell_rect.centerx - ellipsis.get_width() // 2,
                    cell_rect.centery - ellipsis.get_height() // 2,
                ),
            )
            continue

        item_entity = entity_lookup.get(item_name)
        sprite = None
        if item_entity:
            renderable = item_entity.get_component(Renderable)
            if renderable and renderable.sprite_path:
                base_sprite = get_or_load_image(renderer, renderable.sprite_path)
                if base_sprite:
                    sprite_size = max(12, int(min(content_rect.width, content_rect.height) * 0.86))
                    sprite = _fit_trade_item_sprite(base_sprite, sprite_size)

        if sprite:
            surface.blit(
                sprite,
                (
                    content_rect.centerx - sprite.get_width() // 2,
                    content_rect.centery - sprite.get_height() // 2,
                ),
            )
            continue

        short = item_name[:2].upper()
        label = font.render(short, True, (240, 222, 166))
        surface.blit(
            label,
            (
                cell_rect.centerx - label.get_width() // 2,
                cell_rect.centery - label.get_height() // 2,
            ),
        )


def _draw_trade_label(surface: pygame.Surface, font: Any, label: str, center_x: int, y: int) -> None:
    text = font.render(label, True, (255, 235, 156))
    shadow = font.render(label, True, (26, 17, 11))
    x = center_x - text.get_width() // 2
    surface.blit(shadow, (x, y + 1))
    surface.blit(text, (x, y))


def _draw_trade_name_section(
    renderer: "Pygame_Renderer",
    rect: pygame.Rect,
    font: Any,
    label: str,
) -> None:
    section = rect.copy()
    pygame.draw.rect(renderer.effect_surface, (55, 34, 20), section)
    pygame.draw.rect(renderer.effect_surface, (151, 94, 43), section, width=1)
    shine = pygame.Rect(section.left + 1, section.top + 1, max(0, section.width - 2), max(1, section.height // 3))
    pygame.draw.rect(renderer.effect_surface, (97, 61, 31), shine)
    _draw_trade_label(
        renderer.effect_surface,
        font,
        label,
        section.centerx,
        section.centery - font.get_height() // 2,
    )


def _draw_trade_log_line(
    surface: pygame.Surface,
    font: Any,
    text: str,
    x: int,
    y: int,
    max_width: int,
) -> None:
    speaker_color = (255, 235, 156)
    message_color = (246, 231, 196)
    shadow_color = (28, 19, 13)
    if ": " not in text:
        line = _ellipsize_text(font, text, max_width)
        shadow = font.render(line, True, shadow_color)
        rendered = font.render(line, True, message_color)
        surface.blit(shadow, (x + 1, y + 1))
        surface.blit(rendered, (x, y))
        return

    speaker, message = text.split(": ", 1)
    speaker_text = f"{speaker}: "
    speaker_width = font.size(speaker_text)[0]
    message_text = _ellipsize_text(font, message, max(12, max_width - speaker_width))
    speaker_shadow = font.render(speaker_text, True, shadow_color)
    message_shadow = font.render(message_text, True, shadow_color)
    speaker_rendered = font.render(speaker_text, True, speaker_color)
    message_rendered = font.render(message_text, True, message_color)
    surface.blit(speaker_shadow, (x + 1, y + 1))
    surface.blit(message_shadow, (x + speaker_width + 1, y + 1))
    surface.blit(speaker_rendered, (x, y))
    surface.blit(message_rendered, (x + speaker_width, y))


def _draw_trade_window_bg(renderer: "Pygame_Renderer", rect: pygame.Rect) -> None:
    bg = get_scaled_image(renderer, RUSTIC_TRADE_WINDOW_SPRITE, rect.width, rect.height)
    if bg:
        renderer.effect_surface.blit(bg, rect)
    else:
        pygame.draw.rect(renderer.effect_surface, (118, 72, 35), rect)
        pygame.draw.rect(renderer.effect_surface, (222, 184, 118), rect.inflate(-18, -16))


def _public_trade_offer_rect(
    renderer: "Pygame_Renderer",
    entity_position: tuple[int, int],
    width: int,
    height: int,
) -> pygame.Rect:
    tile_s = renderer.tile_size
    margin = max(6, int(tile_s * 0.12))
    center_x = entity_position[0] + tile_s // 2
    above = pygame.Rect(center_x - width // 2, entity_position[1] - height - margin, width, height)
    if above.top >= margin:
        return _clamp_rect_to_surface(above, renderer.effect_surface, margin)
    below = pygame.Rect(center_x - width // 2, entity_position[1] + tile_s + margin, width, height)
    return _clamp_rect_to_surface(below, renderer.effect_surface, margin)


def draw_public_trade_offer_window(
    renderer: "Pygame_Renderer",
    entity_name: str,
    entity_position: tuple[int, int],
    offer: Public_Trade_Offer,
    entity_lookup: dict[str, Entity],
    scale: float,
) -> None:
    tile_s = renderer.tile_size
    title_font = pygame.font.SysFont(None, max(13, int(tile_s * 0.19)), bold=True)
    item_font = pygame.font.SysFont(None, max(11, int(tile_s * 0.18)), bold=True)
    gold = (245, 214, 115)

    cell_size = max(18, int(tile_s * 0.42 * scale))
    grid_size = cell_size * 2
    pad_x = max(9, int(tile_s * 0.13 * scale))
    pad_top = max(10, int(tile_s * 0.15 * scale))
    label_h = title_font.get_height()
    gap = max(3, int(tile_s * 0.05 * scale))
    name_h = label_h + max(4, int(tile_s * 0.06 * scale))
    currency_h = max(15, int(tile_s * 0.20 * scale)) if offer.currency > 0 else 0
    panel_width = max(grid_size + pad_x * 2, int(tile_s * 1.28 * scale))
    panel_height = pad_top + name_h + gap + grid_size + gap + currency_h + max(8, int(tile_s * 0.10 * scale))
    panel_rect = _public_trade_offer_rect(renderer, entity_position, panel_width, panel_height)

    _draw_trade_window_bg(renderer, panel_rect)
    label_h = title_font.get_height()
    label_y = panel_rect.top + max(7, int(tile_s * 0.10 * scale))
    name_rect = pygame.Rect(
        panel_rect.centerx - grid_size // 2,
        label_y,
        grid_size,
        name_h,
    )
    _draw_trade_name_section(renderer, name_rect, title_font, entity_name)

    grid_rect = pygame.Rect(
        panel_rect.centerx - grid_size // 2,
        name_rect.bottom + gap,
        grid_size,
        grid_size,
    )
    _draw_trade_offer_grid(renderer, grid_rect, [item.name for item in offer.items], entity_lookup, item_font, gold)

    if offer.currency > 0:
        currency_y = grid_rect.bottom + gap
        currency_width = _trade_currency_width(renderer, f"{offer.currency:g}", item_font)
        _draw_trade_currency(renderer, grid_rect.centerx - currency_width // 2, currency_y, f"{offer.currency:g}", item_font)


def draw_trade_session_window(
    renderer: "Pygame_Renderer",
    left_position: tuple[int, int],
    right_position: tuple[int, int],
    trade_data: dict[str, Any],
    entity_lookup: dict[str, Entity],
    scale: float,
) -> None:
    tile_s = renderer.tile_size
    left_name = trade_data.get("left", "Trader")
    right_name = trade_data.get("right", "Trader")
    left_items = _trade_items_from_field(trade_data.get("left_offer", "none"))
    right_items = _trade_items_from_field(trade_data.get("right_offer", "none"))
    left_currency = trade_data.get("left_currency", "").strip()
    right_currency = trade_data.get("right_currency", "").strip()
    messages = [_chat_message_text(message) for message in list(trade_data.get("messages", []))[-2:]]

    title_font = pygame.font.SysFont(None, max(13, int(tile_s * 0.20)), bold=True)
    item_font = pygame.font.SysFont(None, max(11, int(tile_s * 0.18)), bold=True)
    status_font = pygame.font.SysFont(None, max(13, int(tile_s * 0.20)), bold=True)
    log_font = pygame.font.SysFont(None, max(12, int(tile_s * 0.18)), bold=True)
    gold = (245, 214, 115)

    pad_x = max(8, int(tile_s * 0.12))
    surface_w = renderer.effect_surface.get_width()
    surface_margin = max(8, int(tile_s * 0.14))
    target_width = int(tile_s * (4.10 if messages else 3.55) * scale)
    available_width = max(96, surface_w - surface_margin * 2)
    panel_width = min(target_width, available_width)
    log_line_gap = max(1, int(tile_s * 0.02))
    log_lines = messages
    log_height = 0
    if log_lines:
        log_height = max(int(tile_s * 0.42), len(log_lines) * log_font.get_height() + max(0, len(log_lines) - 1) * log_line_gap + 8)
    panel_height = max(int(tile_s * 1.62 * scale), 108) + log_height
    panel_rect = _trade_session_rect(renderer, left_position, right_position, panel_width, panel_height)

    _draw_trade_window_bg(renderer, panel_rect)

    center_gap = max(7, int(tile_s * 0.10))
    label_y = panel_rect.top + max(7, int(tile_s * 0.10))

    left_area_left = panel_rect.left + pad_x
    left_area_right = panel_rect.centerx - center_gap
    right_area_left = panel_rect.centerx + center_gap
    right_area_right = panel_rect.right - pad_x
    grid_area_width = min(left_area_right - left_area_left, right_area_right - right_area_left)
    cell_size = max(18, min(int(tile_s * 0.42), grid_area_width // 2))
    grid_size = cell_size * 2
    name_h = title_font.get_height() + max(4, int(tile_s * 0.06))
    grid_y = label_y + name_h + max(3, int(tile_s * 0.04))
    bottom_reserved = log_height + max(8, int(tile_s * 0.10))
    currency_y = min(
        panel_rect.bottom - bottom_reserved - max(21, int(tile_s * 0.29)),
        grid_y + grid_size + max(3, int(tile_s * 0.05)),
    )

    divider_top = panel_rect.top + max(8, int(tile_s * 0.12))
    divider_bottom = panel_rect.bottom - bottom_reserved
    pygame.draw.line(renderer.effect_surface, (139, 90, 44, 120), (panel_rect.centerx, divider_top), (panel_rect.centerx, divider_bottom), width=2)

    left_grid = pygame.Rect(left_area_left + max(0, (left_area_right - left_area_left - grid_size) // 2), grid_y, grid_size, grid_size)
    right_grid = pygame.Rect(right_area_left + max(0, (right_area_right - right_area_left - grid_size) // 2), grid_y, grid_size, grid_size)
    _draw_trade_name_section(renderer, pygame.Rect(left_grid.left, label_y, left_grid.width, name_h), title_font, left_name)
    _draw_trade_name_section(renderer, pygame.Rect(right_grid.left, label_y, right_grid.width, name_h), title_font, right_name)
    _draw_trade_offer_grid(renderer, left_grid, left_items, entity_lookup, item_font, gold)
    _draw_trade_offer_grid(renderer, right_grid, right_items, entity_lookup, item_font, gold)

    left_currency_width = _trade_currency_width(renderer, left_currency, item_font)
    _draw_trade_currency(renderer, left_grid.centerx - left_currency_width // 2, currency_y, left_currency, item_font)
    if right_currency:
        right_currency_width = _trade_currency_width(renderer, right_currency, item_font)
        _draw_trade_currency(renderer, right_grid.centerx - right_currency_width // 2, currency_y, right_currency, item_font)

    if trade_data.get("accepted") == "yes":
        done = status_font.render("DONE", True, (72, 96, 44))
        renderer.effect_surface.blit(done, (panel_rect.centerx - done.get_width() // 2, panel_rect.bottom - bottom_reserved - int(tile_s * 0.26)))

    if log_lines:
        log_rect = pygame.Rect(
            panel_rect.left + pad_x,
            panel_rect.bottom - log_height - max(4, int(tile_s * 0.04)),
            panel_rect.width - pad_x * 2,
            log_height,
        )
        pygame.draw.rect(renderer.effect_surface, (47, 31, 21), log_rect)
        pygame.draw.rect(renderer.effect_surface, (151, 94, 43), log_rect, width=1)
        line_y = log_rect.top + max(4, int(tile_s * 0.04))
        for line in log_lines:
            _draw_trade_log_line(
                renderer.effect_surface,
                log_font,
                line,
                log_rect.left + 4,
                line_y,
                log_rect.width - 8,
            )
            line_y += log_font.get_height() + log_line_gap


def draw_speech_bubbles(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    """Draw speech bubbles above entities using rounded rects and tail polygons."""
    speech_bubbles = collect_speech_bubbles(env)

    # Build entity lookup for getting speech_bubble_scale.
    entities = list(getattr(getattr(env, "state", None), "entities", []))
    entity_by_name = {entity.name: entity for entity in entities}
    entity_lookup = dict(entity_by_name)
    for owner in entity_by_name.values():
        for component in owner.components.values():
            for attr in ("contents", "inventory", "items"):
                items = getattr(component, attr, None)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, Entity):
                            entity_lookup[item.name] = item

    for entity_name, entity in entity_by_name.items():
        if entity_name not in entity_positions:
            continue
        offer = entity.get_component(Public_Trade_Offer)
        if offer is not None and offer.active:
            r = entity.get_component(Renderable)
            scale = getattr(r, "speech_bubble_scale", 1.0) if r else 1.0
            draw_public_trade_offer_window(
                renderer,
                entity_name,
                entity_positions[entity_name],
                offer,
                entity_lookup,
                scale,
            )

    if not speech_bubbles:
        return

    for bubble in speech_bubbles:
        if isinstance(bubble, dict) and bubble.get("_kind") == "chat_session":
            participant_names = [str(name) for name in bubble.get("participant_names", [])]
            participant_positions = [
                entity_positions[name]
                for name in participant_names
                if name in entity_positions
            ]
            if participant_positions:
                scales = []
                for name in participant_names:
                    entity = entity_by_name.get(name)
                    if entity is None:
                        continue
                    renderable = entity.get_component(Renderable)
                    if renderable is not None:
                        scales.append(getattr(renderable, "speech_bubble_scale", 1.0))
                draw_chat_session_window(
                    renderer,
                    participant_positions,
                    participant_names,
                    list(bubble.get("messages", [])),
                    min(scales) if scales else 1.0,
                )
            continue

        entity_name = bubble.get("entity_name")
        text = str(bubble.get("text", "")).strip()
        if not entity_name or not text or entity_name not in entity_positions:
            continue

        # Get per-entity scale from Renderable, default to 1.0
        scale = 1.0
        entity = entity_by_name.get(entity_name)
        if entity:
            r = entity.get_component(Renderable)
            if r:
                scale = getattr(r, "speech_bubble_scale", 1.0)

        # Trade sessions are renderer-published messages with two participants.
        trade_data = parse_trade_message(text)
        if trade_data:
            trade_data["_entity_lookup"] = entity_lookup
            trade_data["messages"] = list(bubble.get("messages", []))
            left_name = trade_data.get("left", entity_name)
            right_name = trade_data.get("right", bubble.get("partner_name", ""))
            if left_name in entity_positions and right_name in entity_positions:
                left_entity = entity_by_name.get(left_name)
                right_entity = entity_by_name.get(right_name)
                left_scale = scale
                right_scale = scale
                if left_entity:
                    left_renderable = left_entity.get_component(Renderable)
                    if left_renderable:
                        left_scale = getattr(left_renderable, "speech_bubble_scale", 1.0)
                if right_entity:
                    right_renderable = right_entity.get_component(Renderable)
                    if right_renderable:
                        right_scale = getattr(right_renderable, "speech_bubble_scale", 1.0)
                draw_trade_session_window(
                    renderer,
                    entity_positions[left_name],
                    entity_positions[right_name],
                    trade_data,
                    entity_lookup,
                    min(left_scale, right_scale),
                )
                continue

        px, py = entity_positions[entity_name]
        anchor_x = px + renderer.tile_size // 2
        anchor_y = py + max(4, renderer.tile_size // 6)

        # Apply scale to bubble dimensions
        bubble_width = max(int(renderer.tile_size * 2.55 * scale), int(140 * scale))
        bubble_height = max(int(renderer.tile_size * 1.18 * scale), int(54 * scale))
        pad_left = max(int(10 * scale), int(renderer.tile_size * 0.18 * scale))
        pad_right = max(int(10 * scale), int(renderer.tile_size * 0.18 * scale))
        pad_top = max(int(8 * scale), int(renderer.tile_size * 0.14 * scale))
        pad_bottom = max(int(9 * scale), int(renderer.tile_size * 0.16 * scale))
        tail_width = max(int(14 * scale), renderer.tile_size // 2)
        tail_height = max(int(10 * scale), int(renderer.tile_size * 0.26 * scale))
        radius = max(int(10 * scale), int(renderer.tile_size * 0.24 * scale))
        text_max_width = bubble_width - pad_left - pad_right
        speech_font, lines = fit_wrapped_text_lines(
            list(renderer.speech_fonts[:-1]) if len(renderer.speech_fonts) > 1 else renderer.speech_fonts,
            text,
            max_width=text_max_width,
            max_lines=3,
        )
        text_surfaces = [speech_font.render(line, True, (18, 16, 14)) for line in lines]
        text_width = max(surface.get_width() for surface in text_surfaces)
        line_gap = max(1, int(renderer.tile_size * 0.02))
        text_height = sum(surface.get_height() for surface in text_surfaces) + max(0, len(text_surfaces) - 1) * line_gap
        bubble_width = max(bubble_width, text_width + pad_left + pad_right)
        bubble_height = max(
            bubble_height,
            text_height + pad_top + pad_bottom,
            int(renderer.tile_size * (0.78 + 0.28 * len(lines))),
        )
        bubble_x = anchor_x - bubble_width // 2
        bubble_y = max(6, anchor_y - bubble_height - tail_height)
        content_left = bubble_x + pad_left
        content_top = bubble_y + pad_top
        content_width = bubble_width - pad_left - pad_right
        content_height = bubble_height - pad_top - pad_bottom

        bubble_rect = pygame.Rect(bubble_x, bubble_y, bubble_width, bubble_height)
        tail = [
            (anchor_x - tail_width // 2, bubble_rect.bottom - 2),
            (anchor_x + tail_width // 2, bubble_rect.bottom - 2),
            (anchor_x, anchor_y),
        ]
        pygame.draw.rect(renderer.effect_surface, (250, 245, 233), bubble_rect, border_radius=radius)
        pygame.draw.rect(renderer.effect_surface, (56, 46, 39), bubble_rect, width=2, border_radius=radius)
        pygame.draw.polygon(renderer.effect_surface, (250, 245, 233), tail)
        pygame.draw.polygon(renderer.effect_surface, (56, 46, 39), tail, width=2)

        text_y = content_top + max(0, (content_height - text_height) // 2)
        for surface in text_surfaces:
            text_x = content_left + max(0, (content_width - surface.get_width()) // 2)
            renderer.effect_surface.blit(surface, (text_x, text_y))
            text_y += surface.get_height() + line_gap



def auto_tile_wall_entities(renderer: "Pygame_Renderer", renderables: list[tuple[int, Entity, Renderable]]) -> None:
    """Update sprite_path for wall entities based on neighbor auto-tiling."""
    wall_positions: set[tuple[int, int]] = set()
    wall_entities: list[tuple[Entity, Renderable]] = []
    for _, entity, renderable in renderables:
        if renderable.wall_set is not None and "wall" in entity.tags:
            try:
                wx, wy = entity.position.x, entity.position.y
            except AttributeError:
                continue
            wall_positions.add((wx, wy))
            wall_entities.append((entity, renderable))
    if not wall_entities:
        return
    for entity, renderable in wall_entities:
        wx, wy = entity.position.x, entity.position.y
        neighbors = wall_neighbor_mask(wx, wy, wall_positions)
        resolved = resolve_wall_sprite(renderer, renderable.wall_set, neighbors)
        if resolved is not None:
            renderable.sprite_path = resolved



def render_environment(renderer: "Pygame_Renderer", env: "Environment") -> None:
    """Render a full frame including background, entities, effects, and HUD."""
    renderer.layout.prepare_env(env)
    update_damage_flash_state(renderer, env)
    background = background_items(env, renderer)
    renderables = visible_renderables(env)
    if getattr(renderer, "selected_entity_name", None) and selected_entity(env, renderer) is None:
        renderer.selected_entity_name = None
    if renderer.camera_focus_entity_name and not any(entity.name == renderer.camera_focus_entity_name for entity in env.state.entities):
        renderer.camera_focus_entity_name = None
        renderer.camera_center = None
    min_world_x, max_world_x, min_world_y, max_world_y = world_bounds(renderer, background, renderables)
    min_x, max_x, min_y, max_y = update_camera_state(
        renderer,
        env,
        min_world_x=min_world_x,
        max_world_x=max_world_x,
        min_world_y=min_world_y,
        max_world_y=max_world_y,
    )

    grid_width = max(1, max_x - min_x + 1)
    grid_height = max(1, max_y - min_y + 1)
    sidebar_lines = list(getattr(env, "hud_sidebar_lines", []))
    selected_action_lines = list(getattr(env, "hud_sidebar_selected_action", []))
    action_lines = list(getattr(env, "hud_sidebar_actions", []))
    needs_sidebar = sidebar_is_allowed(env) and bool(sidebar_lines or selected_action_lines or action_lines)
    requested_sidebar_width = int(getattr(env, "hud_sidebar_width", 380 if needs_sidebar else 0)) if needs_sidebar else 0
    hud_visible = not getattr(env, "hide_bottom_hud", False)
    resolved_tile_size = fitted_tile_size(
        renderer,
        grid_width=grid_width,
        grid_height=grid_height,
        sidebar_width=requested_sidebar_width,
        hud_visible=hud_visible,
    )
    if resolved_tile_size != renderer.tile_size:
        apply_renderer_metrics(renderer, resolved_tile_size)

    sidebar_width = 0
    if needs_sidebar:
        sidebar_width = max(
            280,
            int(round(requested_sidebar_width * (renderer.tile_size / max(1, renderer.base_tile_size)))),
        )
    world_width = renderer.viewport_pad_w + renderer.viewport_pad_e + grid_width * renderer.tile_size
    hud_height = 0 if not hud_visible else renderer.hud_height
    width = world_width + sidebar_width
    height = renderer.viewport_pad_n + renderer.viewport_pad_s + grid_height * renderer.tile_size + hud_height
    ensure_screen_size(renderer, width, height)

    renderer.screen.fill((8, 11, 16))
    world_height = renderer.viewport_pad_n + renderer.viewport_pad_s + grid_height * renderer.tile_size
    renderer.floor_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.shadow_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.entity_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.effect_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.foreground_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.light_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.world_surface = renderer.floor_surface
    renderer.floor_surface.fill((8, 11, 16))
    renderer._last_drawn_entity_rects = {}
    visible_background = [
        item for item in background
        if is_within_visible_bounds(int(item["x"]), int(item["y"]), min_x, max_x, min_y, max_y)
    ]
    los_tiles = visible_tile_set(env, renderer)
    wall_positions = collect_wall_positions(visible_background)

    for item in visible_background:
        x = int(item["x"])
        y = int(item["y"])
        px, py = screen_rect_for_tile(renderer, x, y, min_x, max_y)
        draw_background_tile(renderer, item, px, py, wall_positions=wall_positions)

    auto_tile_wall_entities(renderer, renderables)

    positions: dict[str, tuple[int, int]] = {}
    for _, entity, renderable in renderables:
        world_position = entity_world_position(renderer, entity)
        if world_position is None:
            continue
        x, y = world_position
        if not is_within_visible_bounds(x, y, min_x, max_x, min_y, max_y):
            continue
        position = interpolated_entity_screen_position(
            renderer,
            entity,
            min_x=min_x,
            max_y=max_y,
            renderable=renderable,
        )
        if position is None:
            continue
        px, py = position
        positions[entity.name] = position
        draw_entity(renderer, entity, renderable, px, py)

    draw_hit_effects(renderer, env, positions)
    draw_speech_bubbles(renderer, env, positions)
    draw_visibility_mask(renderer, los_tiles, min_x, max_y)
    draw_selected_entity_card(renderer, env, positions)

    world_x = 0
    renderer.screen.blit(renderer.floor_surface, (world_x, 0))
    renderer.screen.blit(renderer.shadow_surface, (world_x, 0))
    renderer.screen.blit(renderer.entity_surface, (world_x, 0))
    renderer.screen.blit(renderer.effect_surface, (world_x, 0))
    renderer.screen.blit(renderer.light_surface, (world_x, 0), special_flags=pygame.BLEND_RGBA_ADD)
    renderer.screen.blit(renderer.foreground_surface, (world_x, 0))
    draw_world_vignette(renderer, world_x, world_width, world_height)

    draw_hud_panel(renderer, env, world_x, world_width, height)
    draw_sidebar_panel(renderer, env, world_x + world_width, height, sidebar_width)
    draw_end_overlay(renderer, env, world_x, world_width, height - hud_height)
    pygame.display.flip()
