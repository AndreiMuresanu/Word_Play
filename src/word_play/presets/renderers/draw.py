from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity

from .assets import get_or_load_image, get_scaled_image, resolve_wall_sprite
from .wall_geometry import collect_wall_positions, normalize_background_item, screen_rect_for_tile, wall_neighbor_mask, world_bounds
from .renderer import Renderable
from .runtime import apply_renderer_metrics, ensure_screen_size, fitted_tile_size

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import Pygame_Renderer


# Note: Container/Inventory/Crafter imports are done inside functions
# to avoid circular import issues with renderables module


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
    """Allow the right HUD only for single-agent envs or envs with human action components."""
    agents = list(getattr(env, "agents", []) or [])
    if len(agents) == 1:
        return True

    for entity in getattr(getattr(env, "state", None), "entities", []):
        for component in getattr(entity, "components", {}).values():
            if component.__class__.__name__ == "Human_Takes_Action":
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
    renderer.camera_center = None
    renderer.camera_shake_strength = 0.0 if renderer.camera_shake_until <= time.monotonic() else renderer.camera_shake_strength
    return min_world_x, max_world_x, min_world_y, max_world_y


def is_within_visible_bounds(x: int, y: int, min_x: int, max_x: int, min_y: int, max_y: int) -> bool:
    """Report whether a tile lies inside the active camera window."""
    return min_x <= x <= max_x and min_y <= y <= max_y


def visible_tile_set(env: "Environment", renderer: "Pygame_Renderer") -> set[tuple[int, int]] | None:
    """Return environment-level line-of-sight tiles when a focused agent is being inspected."""
    if not getattr(renderer, "camera_focus_entity_name", None):
        return None
    visible_tiles_for = getattr(env, "visible_tiles_for", None)
    if callable(visible_tiles_for):
        return {tuple(tile) for tile in visible_tiles_for(renderer.camera_focus_entity_name)}
    visible_tiles = getattr(env, "visible_tiles", None)
    if not callable(visible_tiles):
        return None
    return {tuple(tile) for tile in visible_tiles()}


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

    # Optional overlays for branch-specific presets. If the corresponding
    # system modules do not exist on this branch, skip these overlays.
    try:
        from word_play.presets.systems.containers import Container
    except Exception:
        Container = None
    if Container is not None:
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
    from word_play.presets.systems.inventory import Inventory
    inventory = entity.get_component(Inventory)
    if inventory is not None:
        inv_list = getattr(inventory, 'contents', [])
        if len(inv_list) > 0 and not getattr(renderable, 'overlay_sprite', None):
            items = inv_list[:2]
            draw_entity_items(renderer, items, px, py, layout_mode="badges", max_items=2, scale=0.50)

    try:
        from word_play.presets.systems.crafter import Crafter
    except Exception:
        Crafter = None
    if Crafter is not None:
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

    try:
        from word_play.presets.systems.containers import Single_Item_Holder
    except Exception:
        Single_Item_Holder = None
    if Single_Item_Holder is not None:
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
        # Draw placeholder square
        import pygame
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
    controls_text = "R: reset | ESC: exit"
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
    """Collect speech bubbles from environment or renderable components.

    Priority:
    1. If env has speech_bubbles attribute, use those directly
    2. Otherwise, scan entity Renderable components for last_message
    """
    # If environment already has defined speech_bubbles, use them
    bubbles = list(getattr(env, "speech_bubbles", []))
    if bubbles:
        return bubbles

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
    """Parse a trade message format: TRADE:|you_offer:X|you_currency:N|they_offer:Y|they_currency:M|you_accepted:yes/no|they_accepted:yes/no|partner:NAME"""
    if not text.startswith("TRADE:|"):
        return None
    try:
        parts = text.split("|")
        result: dict[str, Any] = {}
        for part in parts[1:]:  # Skip "TRADE:"
            if ":" in part:
                key, value = part.split(":", 1)
                result[key] = value
        return result
    except Exception:
        return None


def draw_trade_bubble(
    renderer: "Pygame_Renderer",
    entity_position: tuple[int, int],
    trade_data: dict[str, Any],
    scale: float,
) -> None:
    """Draw an optimized fantasy trade window above the trading agent.

    Features:
    - Smart positioning that avoids screen edges
    - Dynamic sizing based on item count
    - Enhanced parchment theme with shadows
    - Proper sprite scaling and centering
    """
    from .assets import get_or_load_image

    px, py = entity_position
    tile_s = renderer.tile_size
    center_x = px + tile_s // 2
    agent_bottom = py + tile_s

    # Parse trade data from viewer's perspective
    you_offer = trade_data.get("you_offer", "none")
    you_currency = trade_data.get("you_currency", "").strip()
    they_offer = trade_data.get("they_offer", "none")
    they_currency = trade_data.get("they_currency", "").strip()
    you_accepted = trade_data.get("you_accepted", "no") == "yes"
    they_accepted = trade_data.get("they_accepted", "no") == "yes"
    partner = trade_data.get("partner", "Partner")

    # Parse items from offers
    your_items = [i.strip() for i in you_offer.split(",") if i.strip() and i.strip() != "none"]
    their_items = [i.strip() for i in they_offer.split(",") if i.strip() and i.strip() != "none"]
    entity_lookup = trade_data.get("_entity_lookup", {})

    # Calculate dynamic scale based on tile size (base: 64px)
    base_tile = 64
    dynamic_scale = scale * (tile_s / base_tile)

    # Dynamic sizing based on item count
    max_your_items = min(len(your_items), 3)
    max_their_items = min(len(their_items), 3)
    has_currency = bool(you_currency or they_currency)

    # Calculate item slot size based on tile size
    item_size = int(tile_s * 0.45)  # ~29px for 64px tile
    item_spacing = int(tile_s * 0.08)  # ~5px

    # Calculate window dimensions
    header_height = int(tile_s * 0.5)  # ~32px
    item_row_height = item_size + int(tile_s * 0.15)  # ~39px
    currency_row_height = int(tile_s * 0.4) if has_currency else 0  # ~26px
    footer_height = int(tile_s * 0.2)  # ~13px
    pad = int(tile_s * 0.12)  # ~8px

    # Comfortable width based on tiles
    min_width = int(tile_s * 4.5)  # ~288px
    max_width = int(tile_s * 5.5)  # ~352px

    # Calculate required width based on items
    items_width = max(
        max_your_items * (item_size + item_spacing),
        max_their_items * (item_size + item_spacing)
    ) + int(tile_s * 1.5)  # arrow + margins

    bubble_width = max(min_width, min(max_width, items_width))
    bubble_height = header_height + item_row_height + currency_row_height + footer_height + (pad * 3)

    # Smart positioning - try above first, then below if not enough space
    world_height = renderer.effect_surface.get_height()
    desired_y_above = py - bubble_height - int(tile_s * 0.25)
    desired_y_below = agent_bottom + int(tile_s * 0.15)

    if desired_y_above >= int(tile_s * 0.3):  # Above agent if enough space
        bubble_y = desired_y_above
        pointer_from_top = False
    else:  # Below agent
        bubble_y = min(desired_y_below, world_height - bubble_height - int(tile_s * 0.3))
        pointer_from_top = True

    # Horizontal positioning with edge detection
    desired_x = center_x - bubble_width // 2
    world_width = renderer.effect_surface.get_width()
    bubble_x = max(int(tile_s * 0.15), min(desired_x, world_width - bubble_width - int(tile_s * 0.15)))

    bubble_rect = pygame.Rect(bubble_x, bubble_y, bubble_width, bubble_height)

    # Colors - Parchment/Fantasy trading theme
    PARCHMENT_BG = (42, 38, 32)      # Warm dark parchment
    PARCHMENT_LIGHT = (55, 50, 42)   # Lighter for inner
    PARCHMENT_DARK = (32, 28, 24)    # Dark for header bar
    GOLD = (218, 165, 32)            # Royal gold
    GOLD_DIM = (160, 120, 25)        # Dimmed gold for borders
    GOLD_BRIGHT = (255, 215, 100)    # Bright gold for highlights
    COPPER = (184, 115, 51)          # Copper for inactive
    TEXT_CREAM = (240, 235, 220)     # Cream text
    TEXT_GOLD = (255, 220, 120)      # Gold text for headers

    # Background - parchment with subtle gradient
    pygame.draw.rect(renderer.effect_surface, PARCHMENT_BG, bubble_rect, border_radius=int(12 * scale))
    # Inner highlight for depth
    inner_rect = bubble_rect.inflate(int(-4 * scale), int(-4 * scale))
    pygame.draw.rect(renderer.effect_surface, PARCHMENT_LIGHT, inner_rect, border_radius=int(10 * scale))

    # Border - gold when accepted, copper/bronze when not
    if you_accepted and they_accepted:
        border_color = GOLD_BRIGHT
        glow_color = (100, 255, 100, 60)
    elif you_accepted:
        border_color = GOLD
        glow_color = (255, 200, 50, 50)
    else:
        border_color = COPPER
        glow_color = (255, 150, 50, 40)
    pygame.draw.rect(renderer.effect_surface, border_color, bubble_rect, width=int(3 * scale), border_radius=int(12 * scale))
    # Outer glow effect
    glow_rect = bubble_rect.inflate(int(8 * scale), int(8 * scale))
    glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
    pygame.draw.rect(glow_surface, glow_color, pygame.Rect(0, 0, glow_rect.width, glow_rect.height), border_radius=int(14 * scale))
    renderer.effect_surface.blit(glow_surface, (glow_rect.x, glow_rect.y), special_flags=pygame.BLEND_RGBA_ADD)
    
    # Decorative corner flourishes
    def draw_corner_dot(x, y):
        pygame.draw.circle(renderer.effect_surface, border_color, (x, y), int(3 * scale))
        pygame.draw.circle(renderer.effect_surface, GOLD_BRIGHT, (x, y), int(1.5 * scale))
    
    corner_offset = int(8 * scale)
    draw_corner_dot(bubble_rect.left + corner_offset, bubble_rect.top + corner_offset)
    draw_corner_dot(bubble_rect.right - corner_offset, bubble_rect.top + corner_offset)
    draw_corner_dot(bubble_rect.left + corner_offset, bubble_rect.bottom - corner_offset)
    draw_corner_dot(bubble_rect.right - corner_offset, bubble_rect.bottom - corner_offset)

    # Fonts - BIGGER and clearer
    font_size = max(12, int(tile_s * 0.28))  # was 10, now 16
    try:
        font = pygame.font.SysFont("Arial", font_size, bold=True)
    except:
        font = pygame.font.SysFont(None, font_size, bold=True)
    small_font = pygame.font.SysFont(None, max(10, int(tile_s * 0.22)))  # was 9, now 14

    text_color = (220, 215, 200)
    accent_color = (180, 145, 85)
    gold_color = (255, 215, 90)

    y_offset = bubble_rect.top + int(8 * scale)

    # Header bar with partner name - decorative title
    header_height = int(24 * scale)
    header_rect = pygame.Rect(bubble_rect.left + int(3*scale), y_offset, 
                              bubble_rect.width - int(6*scale), header_height)
    # Header background with gradient effect
    pygame.draw.rect(renderer.effect_surface, PARCHMENT_DARK, header_rect, 
                     border_radius=int(6 * scale))
    # Header border
    pygame.draw.rect(renderer.effect_surface, border_color, header_rect, 
                     width=int(1 * scale), border_radius=int(6 * scale))
    
    # Title text
    title_text = f"TRADE: {partner}"
    title_surface = small_font.render(title_text, True, TEXT_GOLD)
    title_x = bubble_rect.centerx - title_surface.get_width() // 2
    title_y = y_offset + (header_height - title_surface.get_height()) // 2
    renderer.effect_surface.blit(title_surface, (title_x, title_y))
    y_offset += header_height + int(8 * scale)

    # Items row - show YOUR items (what you're offering) - larger slots
    item_size = int(tile_s * 0.45)  # Was 16, now 28 for bigger sprites
    item_spacing = int(tile_s * 0.08)  # More spacing
    max_visible = 3  # Show max 3 items instead of 2

    # Calculate total width for centering
    left_items_width = min(len(your_items), max_visible) * (item_size + item_spacing) - item_spacing
    right_items_width = min(len(their_items), max_visible) * (item_size + item_spacing) - item_spacing

    # Items container - centered in the bubble
    # Calculate left section start position (centered in left half)
    left_section_width = left_items_width + (20 * scale)
    items_x = bubble_rect.centerx - int(30 * scale) - left_section_width
    items_y = y_offset

    # Draw your items on the left
    displayed_items = your_items[:max_visible]
    overflow = max(0, len(your_items) - max_visible)

    x_pos = items_x
    # Item slot colors - parchment theme
    SLOT_BG = (35, 42, 35)           # Dark green-gray for empty slot
    SLOT_BORDER = (100, 90, 70)      # Brown border
    SLOT_HIGHLIGHT = (70, 75, 60)    # Inner highlight

    # Gold color for text
    GOLD = (218, 165, 32)            # Royal gold
    GOLD_BRIGHT = (255, 215, 100)    # Bright gold for highlights

    for item_name in displayed_items:
        item_rect = pygame.Rect(x_pos, items_y, item_size, item_size)
        # Draw slot background with border
        pygame.draw.rect(renderer.effect_surface, SLOT_BG, item_rect, border_radius=int(4 * scale))
        pygame.draw.rect(renderer.effect_surface, SLOT_BORDER, item_rect, width=2, border_radius=int(4 * scale))
        # Inner highlight
        inner_slot = item_rect.inflate(int(-4 * scale), int(-4 * scale))
        pygame.draw.rect(renderer.effect_surface, SLOT_HIGHLIGHT, inner_slot, border_radius=int(2 * scale))

        # Try to get sprite - larger display area for better visibility
        item_entity = entity_lookup.get(item_name)
        sprite = None
        if item_entity:
            renderable = item_entity.get_component(Renderable)
            if renderable and renderable.sprite_path:
                # Use full slot size minus padding for sprite
                sprite_size = item_size - 8
                sprite = get_scaled_image(renderer, renderable.sprite_path, sprite_size, sprite_size)
        if sprite:
            # Center the sprite in the slot
            sprite_x = x_pos + (item_size - sprite.get_width()) // 2
            sprite_y = items_y + (item_size - sprite.get_height()) // 2
            renderer.effect_surface.blit(sprite, (sprite_x, sprite_y))
        else:
            # Fallback: abbreviation
            short = item_name[:2].upper()
            abbrev_surf = small_font.render(short, True, (180, 180, 180))
            center_x = x_pos + item_size // 2 - abbrev_surf.get_width() // 2
            center_y = items_y + item_size // 2 - abbrev_surf.get_height() // 2
            renderer.effect_surface.blit(abbrev_surf, (center_x, center_y))

        x_pos += item_size + item_spacing

    if overflow > 0:
        # +N text
        overflow_text = f"+{overflow}"
        overflow_surf = font.render(overflow_text, True, text_color)
        renderer.effect_surface.blit(overflow_surf, (x_pos, items_y + (item_size - overflow_surf.get_height()) // 2))
        x_pos += overflow_surf.get_width() + int(4 * scale)

    # Show "->" separator
    arrow_surf = small_font.render("→", True, accent_color)
    arrow_x = bubble_rect.centerx - arrow_surf.get_width() // 2
    renderer.effect_surface.blit(arrow_surf, (arrow_x, items_y + (item_size - arrow_surf.get_height()) // 2))

    # Their items on the right side (what you're receiving)
    their_displayed = their_items[:max_visible]
    their_overflow = max(0, len(their_items) - max_visible)

    x_pos_right = bubble_rect.right - pad
    if their_overflow > 0:
        x_pos_right -= font.size(f"+{their_overflow}")[0] + int(4 * scale)

    # Draw right-side items from right to left (same parchment theme)
    for i, item_name in enumerate(reversed(their_displayed)):
        item_rect = pygame.Rect(x_pos_right - item_size, items_y, item_size, item_size)
        pygame.draw.rect(renderer.effect_surface, SLOT_BG, item_rect, border_radius=int(4 * scale))
        pygame.draw.rect(renderer.effect_surface, SLOT_BORDER, item_rect, width=2, border_radius=int(4 * scale))
        inner_slot = item_rect.inflate(int(-4 * scale), int(-4 * scale))
        pygame.draw.rect(renderer.effect_surface, SLOT_HIGHLIGHT, inner_slot, border_radius=int(2 * scale))

        item_entity = entity_lookup.get(item_name)
        sprite = None
        if item_entity:
            renderable = item_entity.get_component(Renderable)
            if renderable and renderable.sprite_path:
                # Same larger sprite size for right side
                sprite_size = item_size - 8
                sprite = get_scaled_image(renderer, renderable.sprite_path, sprite_size, sprite_size)
        if sprite:
            # Center the sprite in the slot
            sprite_x = x_pos_right - item_size + (item_size - sprite.get_width()) // 2
            sprite_y = items_y + (item_size - sprite.get_height()) // 2
            renderer.effect_surface.blit(sprite, (sprite_x, sprite_y))
        else:
            short = item_name[:2].upper()
            abbrev_surf = small_font.render(short, True, (180, 180, 180))
            center_x = x_pos_right - item_size // 2 - abbrev_surf.get_width() // 2
            center_y = items_y + item_size // 2 - abbrev_surf.get_height() // 2
            renderer.effect_surface.blit(abbrev_surf, (center_x, center_y))

        x_pos_right -= item_size + item_spacing

    if their_overflow > 0:
        overflow_text = f"+{their_overflow}"
        overflow_surf = font.render(overflow_text, True, text_color)
        renderer.effect_surface.blit(overflow_surf, (x_pos_right - overflow_surf.get_width(), items_y + (item_size - overflow_surf.get_height()) // 2))


    # Currency row
    if you_currency or they_currency:
        y_offset += item_size + int(8 * scale)

    # Draw currency you offer
    if you_currency:
        coin_size = int(20 * scale)
        coin_x = bubble_rect.centerx - int(50 * scale) - coin_size
        coin_rect = pygame.Rect(coin_x, y_offset, coin_size, coin_size)
        # Gold coin with gradient
        pygame.draw.ellipse(renderer.effect_surface, (180, 140, 30), coin_rect)
        pygame.draw.ellipse(renderer.effect_surface, (255, 220, 80), coin_rect.inflate(int(-2*scale), int(-2*scale)))
        pygame.draw.ellipse(renderer.effect_surface, (200, 160, 40), coin_rect, width=int(2*scale))
        # "G" icon
        coin_font = pygame.font.SysFont(None, int(12 * scale), bold=True)
        coin_surf = coin_font.render("G", True, (80, 60, 20))
        coin_text_x = coin_rect.centerx - coin_surf.get_width() // 2
        coin_text_y = coin_rect.centery - coin_surf.get_height() // 2
        renderer.effect_surface.blit(coin_surf, (coin_text_x, coin_text_y))

    # Draw acceptance indicators
    if you_accepted:
        check_text = "OK" if not they_accepted else "DONE"
        check_color = GOLD_BRIGHT if they_accepted else GOLD
        check_surf = font.render(check_text, True, check_color)
        check_x = bubble_rect.centerx - check_surf.get_width() // 2
        check_y = y_offset - int(4 * scale)
        renderer.effect_surface.blit(check_surf, (check_x, check_y))

    # Draw smart pointer - adapts to bubble position
    pointer_width = int(tile_s * 0.15)  # ~10px
    pointer_height = int(tile_s * 0.12)  # ~8px

    if pointer_from_top:
        # Pointer pointing UP (bubble is below agent)
        tail = [
            (center_x, bubble_rect.top + 2),
            (center_x - pointer_width // 2, bubble_rect.top - pointer_height),
            (center_x + pointer_width // 2, bubble_rect.top - pointer_height),
        ]
    else:
        # Pointer pointing DOWN (bubble is above agent)
        tail = [
            (center_x, bubble_rect.bottom - 2),
            (center_x - pointer_width // 2, bubble_rect.bottom + pointer_height),
            (center_x + pointer_width // 2, bubble_rect.bottom + pointer_height),
        ]

    pygame.draw.polygon(renderer.effect_surface, (32, 38, 48), tail)
    pygame.draw.polygon(renderer.effect_surface, border_color, tail, width=int(tile_s * 0.03))


def draw_speech_bubbles(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    """Draw speech bubbles above entities using rounded rects and tail polygons."""
    speech_bubbles = collect_speech_bubbles(env)
    if not speech_bubbles:
        return

    # Build entity lookup for getting speech_bubble_scale
    entity_by_name = {e.name: e for e in getattr(env, "state", None).entities if hasattr(env, "state")}

    for bubble in speech_bubbles:
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

            # Check if this is a trade message
        trade_data = parse_trade_message(text)
        if trade_data:
            # Get entity lookup for accessing items
            entity_lookup = {e.name: e for e in getattr(env, "state", None).entities if hasattr(env, "state")}
            trade_data["_entity_lookup"] = entity_lookup
            entity = entity_by_name.get(entity_name)
            if entity and entity_name in entity_positions:
                draw_trade_bubble(renderer, entity_positions[entity_name], trade_data, scale)
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
    from .assets import resolve_wall_sprite
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
