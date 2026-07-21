from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity
from word_play.presets.systems.inventory import Inventory

from .assets import get_or_load_image, get_scaled_image, resolve_wall_sprite
from .wall_geometry import collect_wall_positions, screen_rect_for_tile, wall_neighbor_mask, world_bounds
from .renderable import Renderable
from .runtime import apply_renderer_metrics, ensure_screen_size, fitted_tile_size, focused_radius, pygame_runtime

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import Pygame_Renderer


def renderable_component(entity: Any) -> Renderable | None:
    get_component = getattr(entity, "get_component", None)
    if callable(get_component):
        return get_component(Renderable)
    return None


def scene_metadata(scene: Any, key: str, default: Any = None) -> Any:
    return scene.metadata.get(key, default)


def sidebar_state(scene: Any) -> dict[str, Any]:
    value = scene_metadata(scene, "ui.sidebar", {})
    if isinstance(value, dict):
        return value
    return {}


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


def entity_inventory_entries(entity: Entity) -> list[dict[str, Any]]:
    """Return inventory entries with names, counts, and sprite hints for the inspector card."""
    entries: list[dict[str, Any]] = []
    inventory_component = entity.get_component(Inventory)
    if inventory_component is None:
        return entries

    aggregated: dict[tuple[str, str | None], int] = {}
    for item in inventory_component.inventory:
        item_name = getattr(item, "name", str(item))
        item_renderable = renderable_component(item)
        sprite_name = None if item_renderable is None else item_renderable.sprite_path
        key = (item_name, sprite_name)
        aggregated[key] = aggregated.get(key, 0) + 1

    for (name, sprite_name), count in aggregated.items():
        entries.append({"name": name, "count": count, "sprite": sprite_name})
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
    selected = pygame_runtime(renderer).view.selected_entity
    if selected is None:
        return None
    return selected if selected in env.state.entities else None


def update_damage_flash_state(renderer: "Pygame_Renderer", env: "Environment", scene: Any) -> None:
    """Track recent health drops so damaged entities can flash briefly."""
    effects = pygame_runtime(renderer).effects
    now = time.monotonic()
    active_entities = set(env.state.entities)
    effects.damage_flash_until = {
        entity: until
        for entity, until in effects.damage_flash_until.items()
        if entity in active_entities and until > now
    }
    current_step = int(scene_metadata(scene, "simulation.step", getattr(env, "cur_step", 0)))
    for hit_payload in scene.layers.get("effects.entity_hits", []):
        entity = hit_payload.get("entity") if isinstance(hit_payload, dict) else hit_payload
        visible_step = hit_payload.get("step") if isinstance(hit_payload, dict) else None
        if entity not in active_entities:
            continue
        if visible_step is not None and int(visible_step) != current_step:
            continue
        effects.damage_flash_until[entity] = max(
                effects.damage_flash_until.get(entity, 0.0),
                now + 1.0,
        )

    next_health_values: dict[Entity, float] = {}
    for entity in env.state.entities:
        health_value = entity_health_value(entity)
        if health_value is None:
            continue
        next_health_values[entity] = health_value
        previous_value = effects.last_health_values.get(entity)
        if previous_value is not None and health_value < previous_value:
            effects.damage_flash_until[entity] = now + 1.0
            effects.camera_shake_until = max(effects.camera_shake_until, now + 0.22)
            effects.camera_shake_strength = max(effects.camera_shake_strength, renderer.tile_size * 0.12)

    effects.last_health_values = next_health_values


def entity_world_position(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity: Entity,
) -> tuple[int, int] | None:
    """Return an entity's tile position in renderer world coordinates."""
    position = getattr(entity, "position", None)
    if position is None:
        return None
    x, y = renderer.layout.screen_position(entity, env, renderer.render_context)
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
    runtime = pygame_runtime(renderer)
    view = runtime.view
    effects = runtime.effects
    focused = view.camera_focus_entity
    if focused in env.state.entities:
        position = entity_world_position(renderer, env, focused)
        if position is not None:
            focus_x, focus_y = position
            radius = focused_radius(env, renderer)
            view.camera_focus_radius_tiles = radius
            effects.camera_shake_strength = (
                0.0 if effects.camera_shake_until <= time.monotonic() else effects.camera_shake_strength
            )
            return (
                *centered_camera_axis(focus_x, radius, min_world_x, max_world_x),
                *centered_camera_axis(focus_y, radius, min_world_y, max_world_y),
            )

    effects.camera_shake_strength = 0.0 if effects.camera_shake_until <= time.monotonic() else effects.camera_shake_strength
    return min_world_x, max_world_x, min_world_y, max_world_y


def centered_camera_axis(center: int, radius: int, min_world: int, max_world: int) -> tuple[int, int]:
    """Clamp a focused camera axis to the world without shrinking near edges."""
    size = radius * 2 + 1
    world_size = max_world - min_world + 1
    if world_size <= size:
        return min_world, max_world

    min_bound = center - radius
    max_bound = min_bound + size - 1
    if min_bound < min_world:
        min_bound = min_world
        max_bound = min_bound + size - 1
    if max_bound > max_world:
        max_bound = max_world
        min_bound = max_bound - size + 1
    return min_bound, max_bound


def is_within_visible_bounds(x: int, y: int, min_x: int, max_x: int, min_y: int, max_y: int) -> bool:
    """Report whether a tile lies inside the active camera window."""
    return min_x <= x <= max_x and min_y <= y <= max_y


def flash_tinted_surface(image: Any, *, tint: tuple[int, int, int], alpha: int) -> Any:
    """Return a tinted copy of a sprite for temporary visual effects."""
    tinted = image.copy()
    overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
    overlay.fill((*tint, alpha))
    tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted


def interpolated_entity_screen_position(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity: Entity,
    *,
    min_x: int,
    max_y: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> tuple[int, int] | None:
    """Get entity screen position - NO interpolation, NO bobbing."""
    world_position = entity_world_position(renderer, env, entity)
    if world_position is None:
        return None

    # Direct position - no interpolation, no smoothing, no bobbing
    px, py = screen_rect_for_tile(renderer, world_position[0], world_position[1], min_x, max_y)
    return px + offset_x, py + offset_y


def overlap_grid_dimensions(count: int) -> tuple[int, int]:
    """Choose a compact sub-grid for entities sharing one tile."""
    if count <= 1:
        return 1, 1
    if count <= 2:
        return 2, 1
    if count <= 4:
        return 2, 2
    if count <= 9:
        return 3, 3
    columns = max(1, math.ceil(math.sqrt(count)))
    return columns, math.ceil(count / columns)


def centered_grid_slot(index: int, count: int, columns: int) -> tuple[int, int, int]:
    """Return col, row, and occupied slots in the row for centered partial rows."""
    row = index // columns
    col = index % columns
    remaining = count - row * columns
    row_slots = max(1, min(columns, remaining))
    return col, row, row_slots


def shared_tile_entity_rect(
    renderer: "Pygame_Renderer",
    tile_px: int,
    tile_py: int,
    *,
    index: int,
    count: int,
) -> pygame.Rect:
    """Return the sprite rect for one entity inside a shared tile."""
    if count <= 1:
        return pygame.Rect(tile_px, tile_py, renderer.tile_size, renderer.tile_size)

    columns, rows = overlap_grid_dimensions(count)
    col, row, row_slots = centered_grid_slot(index, count, columns)
    cell_width = renderer.tile_size / columns
    cell_height = renderer.tile_size / rows
    size = max(16, int(min(cell_width, cell_height) * 0.94))
    row_offset = (columns - row_slots) * cell_width / 2
    px = tile_px + int(row_offset + col * cell_width + (cell_width - size) / 2)
    py = tile_py + int(row * cell_height + (cell_height - size) / 2)
    return pygame.Rect(px, py, size, size)


def draw_focus_ring(renderer: "Pygame_Renderer", entity: Entity, px: int, py: int, size: int | None = None) -> None:
    """Highlight the focused agent so the camera mode is visually obvious."""
    if pygame_runtime(renderer).view.camera_focus_entity is not entity:
        return
    entity_size = renderer.tile_size if size is None else size
    ring_rect = pygame.Rect(px - 4, py - 4, entity_size + 8, entity_size + 8)
    pygame.draw.rect(renderer.effect_surface, renderer.focus_outline_color, ring_rect, width=3, border_radius=10)


def draw_selection_ring(renderer: "Pygame_Renderer", entity: Entity, px: int, py: int, size: int | None = None) -> None:
    """Highlight the selected entity so inspection is visually anchored."""
    if pygame_runtime(renderer).view.selected_entity is not entity:
        return
    entity_size = renderer.tile_size if size is None else size
    ring_rect = pygame.Rect(px - 7, py - 7, entity_size + 14, entity_size + 14)
    glow = pygame.Surface((ring_rect.width + 12, ring_rect.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (*renderer.selection_outline_color, 58), glow.get_rect(), width=8, border_radius=16)
    renderer.effect_surface.blit(glow, (ring_rect.x - 6, ring_rect.y - 6))
    pygame.draw.rect(renderer.effect_surface, renderer.selection_outline_color, ring_rect, width=3, border_radius=12)


def draw_selected_entity_card(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[Entity, tuple[int, int]],
) -> None:
    """Draw a floating inspector card above the selected entity."""
    inspected = selected_entity(env, renderer)
    if inspected is None:
        return

    position = entity_positions.get(inspected)
    if position is None:
        return

    px, py = position
    entity_rect = pygame_runtime(renderer).view.last_drawn_entity_rects.get(
        inspected,
        pygame.Rect(px, py, renderer.tile_size, renderer.tile_size),
    )
    stats = entity_primary_stats(inspected, env)
    inventory_entries = entity_inventory_entries(inspected)
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
    card_x = entity_rect.centerx - card_width // 2
    card_y = entity_rect.top - card_height - tail_height - metrics["outer_pad"]

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

    tail_anchor_x = entity_rect.centerx
    tail_anchor_x = max(card_rect.left + 24, min(tail_anchor_x, card_rect.right - 24))
    tail = [
        (tail_anchor_x - 12, card_rect.bottom - 2),
        (tail_anchor_x + 12, card_rect.bottom - 2),
        (entity_rect.centerx, entity_rect.top - 8),
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
    renderable = renderable_component(inspected)
    if renderable is not None:
        sprite_name = renderable.sprite_path
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
    max_items: int = 2,
    scale: float = 0.50,
    sprite_size: int | None = None,
) -> None:
    """Draw inventory item badges on an entity."""
    if not items or max_items <= 0:
        return

    tile_s = renderer.tile_size if sprite_size is None else sprite_size
    item_size = max(14, int(tile_s * scale))
    positions = [
        (px + tile_s - item_size - 2, py + 2),
        (px + 2, py + tile_s - item_size - 2),
    ]

    for idx, item in enumerate(items[:max_items]):
        if idx >= len(positions):
            break
        draw_x, draw_y = positions[idx]

        renderable = renderable_component(item)
        if renderable is None or not renderable.sprite_path:
            continue

        image = get_scaled_image(renderer, renderable.sprite_path, item_size, item_size)
        if image is not None:
            renderer.effect_surface.blit(image, (draw_x, draw_y))


def draw_entity(
    renderer: "Pygame_Renderer",
    entity: Entity,
    renderable: Any,
    px: int,
    py: int,
    *,
    draw_size: int | None = None,
    sprite_name_override: str | None = None,
) -> None:
    """Draw an entity sprite, including damage flash and optional overlay."""
    sprite_size = draw_size or renderer.tile_size
    sprite_name = sprite_name_override or renderable.sprite_path
    image = get_or_load_image(renderer, sprite_name)
    if image is None:
        raise FileNotFoundError(
            f"Sprite renderer expected a valid sprite path for '{entity.name}', but could not resolve '{sprite_name}'."
        )
    scaled_image = get_scaled_image(renderer, sprite_name, sprite_size, sprite_size)
    if scaled_image is None:
        raise FileNotFoundError(
            f"Sprite renderer expected a valid sprite path for '{entity.name}', but could not resolve '{sprite_name}'."
        )
    flash_until = pygame_runtime(renderer).effects.damage_flash_until.get(entity, 0.0)
    if flash_until > time.monotonic():
        scaled_image = flash_tinted_surface(scaled_image, tint=(190, 20, 20), alpha=140)
    is_wall = renderable.wall_set is not None
    if not is_wall:
        shadow_width = max(14, int(sprite_size * 0.72))
        shadow_height = max(8, int(sprite_size * 0.24))
        shadow = pygame.Surface((shadow_width, shadow_height), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 72), shadow.get_rect())
        shadow_x = px + (sprite_size - shadow_width) // 2
        shadow_y = py + sprite_size - shadow_height // 2 - max(2, sprite_size // 12)
        renderer.shadow_surface.blit(shadow, (shadow_x, shadow_y))
    renderer.entity_surface.blit(scaled_image, (px, py))
    pygame_runtime(renderer).view.last_drawn_entity_rects[entity] = pygame.Rect(px, py, sprite_size, sprite_size)
    draw_selection_ring(renderer, entity, px, py, sprite_size)
    draw_focus_ring(renderer, entity, px, py, sprite_size)

    overlay_sprite = renderable.overlay_sprite
    overlay_mode = getattr(renderable, "overlay_mode", "badge")
    overlay_scale = getattr(renderable, "overlay_scale", None)
    if overlay_sprite is None:
        inventory = entity.get_component(Inventory)
        held_item = None if inventory is None or not inventory.inventory else inventory.inventory[0]
        held_renderable = None if held_item is None else renderable_component(held_item)
        if held_renderable is not None and held_renderable.sprite_path:
            overlay_sprite = held_renderable.sprite_path
            overlay_mode = "badge"
            overlay_scale = 0.28

    if overlay_sprite:
        mode = overlay_mode
        scale = overlay_scale
        if mode == "full":
            overlay_size = sprite_size
            anchor = "top_left"
        elif mode == "center":
            ratio = scale if scale is not None else 0.72
            overlay_size = max(20, int(sprite_size * ratio))
            anchor = "center"
        else:
            ratio = scale if scale is not None else 0.32
            overlay_size = max(14, int(sprite_size * ratio))
            anchor = "top_right"
        overlay = get_scaled_image(renderer, overlay_sprite, overlay_size, overlay_size)
        if overlay is not None:
            if anchor == "top_left":
                overlay_pos = (px, py)
            elif anchor == "top_right":
                overlay_pos = (px + sprite_size - overlay_size, py)
            else:
                overlay_pos = (px + (sprite_size - overlay_size) // 2, py + (sprite_size - overlay_size) // 2)
            renderer.effect_surface.blit(overlay, overlay_pos)

    # Inventory overlay
    inventory = entity.get_component(Inventory)
    if inventory is not None:
        inv_list = inventory.inventory
        if len(inv_list) > 0 and overlay_sprite is None:
            items = inv_list[:2]
            draw_entity_items(renderer, items, px, py, sprite_size=sprite_size)


def draw_hit_effects(
    renderer: "Pygame_Renderer",
    scene: Any,
    entity_positions: dict[Entity, tuple[int, int]],
) -> None:
    """Draw transient hit-effect sprites centered on affected entities."""
    hit_effects = scene.layers.get("effects.entity_hits", [])
    if not hit_effects:
        return

    current_step = int(scene_metadata(scene, "simulation.step", 0))
    for effect in hit_effects:
        if not isinstance(effect, dict):
            continue
        entity = effect.get("entity")
        sprite_name = effect.get("sprite")
        visible_step = effect.get("step")
        if visible_step is not None and int(visible_step) != current_step:
            continue
        if entity not in entity_positions:
            continue

        px, py = entity_positions[entity]
        entity_rect = pygame_runtime(renderer).view.last_drawn_entity_rects.get(
            entity,
            pygame.Rect(px, py, renderer.tile_size, renderer.tile_size),
        )
        ratio = float(effect.get("scale", 0.75))
        effect_size = max(20, int(renderer.tile_size * ratio))
        if sprite_name:
            previous_world_surface = renderer.world_surface
            renderer.world_surface = renderer.effect_surface
            try:
                blit_scaled_sprite(
                    renderer,
                    str(sprite_name),
                    entity_rect.centerx - renderer.tile_size // 2,
                    entity_rect.centery - renderer.tile_size // 2,
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
                entity_rect.centerx + offset_x - 2,
                entity_rect.centery + offset_y - 2,
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
        rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
        pygame.draw.rect(renderer.floor_surface, (40, 50, 60), rect)
        pygame.draw.rect(renderer.floor_surface, (60, 70, 80), rect, 1)
        return

    # Draw the image
    renderer.floor_surface.blit(image, (px, py))

def draw_hud_panel(renderer: "Pygame_Renderer", scene: Any, x_offset: int, width: int, height: int) -> None:
    """Render the bottom HUD panel with step counter, mode, and controls."""
    if not bool(scene_metadata(scene, "ui.hud_visible", True)):
        return

    hud_top = height - renderer.hud_height
    panel_rect = pygame.Rect(x_offset, hud_top, width, renderer.hud_height)
    pygame.draw.rect(renderer.screen, (14, 17, 24), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, hud_top), (x_offset + width, hud_top), 2)

    # Step counter and mode
    step = scene_metadata(scene, "simulation.step", 0)
    episode_length = scene_metadata(scene, "simulation.episode_length")
    current_phase = scene_metadata(scene, "hud.mode")
    score = scene_metadata(scene, "hud.score")
    is_replay = bool(scene_metadata(scene, "simulation.is_replay", False))

    header_text = f"Step: {step}"
    if episode_length:
        header_text += f" / {episode_length}"
    if score is not None:
        header_text += f" | Score: {score}"
    if is_replay:
        header_text += " | Replay"
    if current_phase is not None:
        header_text += f" | Mode: {current_phase}"

    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (x_offset + renderer.margin, hud_top + 16))

    # Controls hint - minimal
    if is_replay:
        controls_text = "Space: play/pause | Left/Right: step | Home/End: jump | R: restart | ESC: exit"
    elif sidebar_state(scene):
        controls_text = (
            "Left click entity: inspect | Right click entity: follow/unfollow | "
            "Terminal: wheel/PgUp/PgDn scroll | ESC: exit"
        )
    else:
        controls_text = (
            "Left click entity: inspect | Right click entity: follow/unfollow | "
            "Terminal: wheel/PgUp/PgDn scroll | R: reset | ESC: exit"
        )
    for line_index, line in enumerate(wrap_text_lines(renderer.small_font, controls_text, width - renderer.margin * 2)[:2]):
        controls = renderer.small_font.render(line, True, (150, 160, 180))
        renderer.screen.blit(controls, (x_offset + renderer.margin, hud_top + 48 + line_index * renderer.small_font.get_linesize()))

def draw_sidebar_panel(
    renderer: "Pygame_Renderer",
    scene: Any,
    x_offset: int,
    y_offset: int,
    width: int,
    height: int,
) -> None:
    """Render an optional right-hand sidebar with agent observations and options."""
    if width <= 0 or height <= 0:
        return

    panel_rect = pygame.Rect(x_offset, y_offset, width, height)
    pygame.draw.rect(renderer.screen, (12, 15, 21), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, y_offset), (x_offset, y_offset + height), 2)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, y_offset), (x_offset + width, y_offset), 2)

    observation_font = getattr(renderer, "sidebar_font", renderer.small_font)

    sidebar = sidebar_state(scene)
    header_text = sidebar.get("header") or "Agent View"
    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (x_offset + 16, y_offset + 14))

    sidebar_lines = list(sidebar.get("lines", []))
    selected_action_lines = list(sidebar.get("selected_action", []))
    action_lines = list(sidebar.get("actions", []))
    compact_observation = bool(sidebar.get("compact_observation", False))
    y = y_offset + 48
    observation_line_height = observation_font.get_linesize() + 3
    action_line_height = renderer.small_font.get_linesize() + 4
    max_width = width - 32
    top_limit = max(y, y_offset + height - 26)

    if not compact_observation:
        column_x = x_offset + 16
        column_y = y
        column_lines = [
            *action_lines,
            *([""] if action_lines and selected_action_lines else []),
            *selected_action_lines,
            *([""] if (action_lines or selected_action_lines) and sidebar_lines else []),
            *sidebar_lines,
        ]
        for message in column_lines:
            wrapped = wrap_text_lines(renderer.small_font, str(message), max_width=max_width)
            for wrapped_line in wrapped:
                if column_y > top_limit:
                    return
                if wrapped_line:
                    color = (235, 213, 154) if wrapped_line == "Possible Actions:" else (189, 196, 206)
                    surface = renderer.small_font.render(wrapped_line, True, color)
                    renderer.screen.blit(surface, (column_x, column_y))
                column_y += action_line_height
        return

    column_gap = 18
    column_width = max(120, (max_width - column_gap) // 2)
    midpoint = (len(sidebar_lines) + 1) // 2
    sidebar_columns = [
        [*action_lines, "", *selected_action_lines, "", *sidebar_lines[:midpoint]],
        sidebar_lines[midpoint:],
    ]
    column_bottoms = [y]

    for column_index, column_lines in enumerate(sidebar_columns):
        column_x = x_offset + 16 + column_index * (column_width + column_gap)
        column_y = y
        for message in column_lines:
            is_action_line = column_index == 0 and message in action_lines + selected_action_lines
            font = renderer.small_font if is_action_line else observation_font
            line_height = action_line_height if is_action_line else observation_line_height
            wrapped = wrap_text_lines(font, str(message), max_width=column_width)
            for wrapped_line in wrapped:
                if column_y > top_limit:
                    break
                if wrapped_line:
                    color = (235, 213, 154) if wrapped_line == "Possible Actions:" else (189, 196, 206)
                    surface = font.render(wrapped_line, True, color)
                    renderer.screen.blit(surface, (column_x, column_y))
                column_y += line_height
            if column_y > top_limit:
                break
        column_y += 4
        column_bottoms.append(column_y)

    y = max(column_bottoms)


def draw_end_overlay(renderer: "Pygame_Renderer", scene: Any, world_x: int, world_width: int, world_height: int) -> None:
    """Draw a centered overlay when the environment reaches a terminal state."""
    overlay_state = scene_metadata(scene, "ui.completion_overlay", {})
    if not isinstance(overlay_state, dict) or not bool(overlay_state.get("visible", False)):
        return

    title = str(overlay_state.get("title", "Experiment Completed"))
    subtitle = str(overlay_state.get("subtitle", "The scheduled run has finished."))
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


def wrap_text_block_lines(font: Any, text: str, max_width: int) -> list[str]:
    """Wrap multi-line text while preserving explicit line breaks."""
    wrapped_lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if not raw_line.strip():
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(wrap_text_lines(font, raw_line, max_width=max_width))
    return wrapped_lines or [""]


def terminal_history_lines(renderer: "Pygame_Renderer", prompt_state: Any, max_width: int) -> list[str]:
    """Build wrapped terminal transcript lines."""
    lines: list[str] = []
    for block in prompt_state.history_blocks:
        if block == "":
            lines.append("")
            continue
        lines.extend(wrap_text_block_lines(renderer.small_font, str(block), max_width=max_width))
    if not lines:
        return ["Human terminal ready."]
    return lines


def draw_text_terminal_panel(
    renderer: "Pygame_Renderer",
    *,
    x_offset: int,
    width: int,
    y_offset: int,
    height: int,
) -> None:
    """Draw a persistent terminal-style panel to the right of the world view."""
    prompt = pygame_runtime(renderer).prompt
    panel_rect = pygame.Rect(x_offset, y_offset, width, height)
    prompt.panel_rect = panel_rect

    pygame.draw.rect(renderer.screen, (10, 13, 18), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, y_offset), (x_offset, y_offset + height), 2)
    pygame.draw.line(renderer.screen, (44, 56, 74), (x_offset, y_offset), (x_offset + width, y_offset), 2)

    pad_x = 18
    pad_y = 14
    title_text = prompt.title if prompt.active else "Terminal"
    subtitle_text = "human input active" if prompt.active else "latest human testing output"
    title_surface = renderer.hud_font.render(title_text, True, (245, 247, 250))
    subtitle_surface = renderer.small_font.render(subtitle_text, True, (145, 169, 194))
    renderer.screen.blit(title_surface, (panel_rect.x + pad_x, panel_rect.y + pad_y))
    renderer.screen.blit(
        subtitle_surface,
        (panel_rect.x + pad_x + title_surface.get_width() + 16, panel_rect.y + pad_y + 4),
    )

    footer_text = "Mouse wheel / PgUp / PgDn scroll | Enter submit | Esc cancel"
    footer_surface = renderer.small_font.render(footer_text, True, (153, 163, 178))
    footer_y = panel_rect.bottom - footer_surface.get_height() - 8
    renderer.screen.blit(footer_surface, (panel_rect.x + pad_x, footer_y))

    input_height = max(42, renderer.hud_font.get_linesize() + 18)
    input_rect = pygame.Rect(
        panel_rect.x + pad_x,
        footer_y - input_height - 10,
        panel_rect.width - pad_x * 2,
        input_height,
    )
    pygame.draw.rect(renderer.screen, (13, 16, 22), input_rect, border_radius=10)
    pygame.draw.rect(renderer.screen, (88, 102, 126), input_rect, width=2, border_radius=10)

    prefix_text = prompt.prompt if prompt.active else "> "
    prefix_surface = renderer.hud_font.render(prefix_text, True, (245, 247, 250))
    prefix_x = input_rect.x + 12
    prefix_y = input_rect.y + (input_rect.height - prefix_surface.get_height()) // 2
    renderer.screen.blit(prefix_surface, (prefix_x, prefix_y))

    if prompt.active:
        cursor = "_" if int(time.monotonic() * 2) % 2 == 0 else " "
        input_text = prompt.input_text + cursor
        input_color = (232, 236, 243)
    else:
        input_text = "Waiting for the next human prompt..."
        input_color = (124, 136, 154)
    max_input_width = input_rect.width - 24 - prefix_surface.get_width()
    visible_text = input_text
    while visible_text and renderer.hud_font.size(visible_text)[0] > max_input_width:
        visible_text = visible_text[1:]
    input_surface = renderer.hud_font.render(visible_text, True, input_color)
    renderer.screen.blit(
        input_surface,
        (prefix_x + prefix_surface.get_width(), input_rect.y + (input_rect.height - input_surface.get_height()) // 2),
    )

    transcript_top = panel_rect.y + pad_y + title_surface.get_height() + 18
    transcript_bottom = input_rect.y - 10
    transcript_rect = pygame.Rect(
        panel_rect.x + pad_x,
        transcript_top,
        panel_rect.width - pad_x * 2,
        max(20, transcript_bottom - transcript_top),
    )
    pygame.draw.rect(renderer.screen, (14, 18, 26), transcript_rect, border_radius=10)
    pygame.draw.rect(renderer.screen, (42, 50, 66), transcript_rect, width=1, border_radius=10)

    line_height = renderer.small_font.get_linesize() + 4
    visible_line_count = max(1, (transcript_rect.height - 12) // line_height)
    transcript_lines = terminal_history_lines(renderer, prompt, transcript_rect.width - 20)
    max_offset = max(0, len(transcript_lines) - visible_line_count)
    prompt.scroll_lines = max(0, min(prompt.scroll_lines, max_offset))
    start_index = prompt.scroll_lines
    end_index = min(len(transcript_lines), start_index + visible_line_count)
    line_y = transcript_rect.y + 8
    for line in transcript_lines[start_index:end_index]:
        if line:
            surface = renderer.small_font.render(line, True, (207, 214, 224))
            renderer.screen.blit(surface, (transcript_rect.x + 10, line_y))
        line_y += line_height

    if max_offset > 0:
        track_rect = pygame.Rect(transcript_rect.right - 10, transcript_rect.y + 8, 4, transcript_rect.height - 16)
        pygame.draw.rect(renderer.screen, (36, 44, 58), track_rect, border_radius=4)
        thumb_height = max(18, int(track_rect.height * (visible_line_count / max(1, len(transcript_lines)))))
        scroll_ratio = start_index / max(1, max_offset)
        thumb_y = track_rect.y + int((track_rect.height - thumb_height) * scroll_ratio)
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
        pygame.draw.rect(renderer.screen, renderer.selection_panel_accent, thumb_rect, border_radius=4)


def draw_world_vignette(renderer: "Pygame_Renderer", world_x: int, world_width: int, world_height: int) -> None:
    """Apply a subtle darkening toward the edges of the world view."""
    cache_key = (world_width, world_height)
    session = pygame_runtime(renderer).session
    overlay = session.vignette_cache.get(cache_key)
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
        session.vignette_cache[cache_key] = overlay
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


def speech_step_is_visible(current_step: int, visible_step: Any) -> bool:
    try:
        step_value = int(visible_step)
    except (TypeError, ValueError):
        return True
    return step_value in (current_step, current_step + 1)


def collect_speech_bubbles(scene: Any) -> list[dict[str, Any]]:
    """Collect speech bubble payloads published into the renderer state."""
    current_step = int(scene_metadata(scene, "simulation.step", 0))
    bubbles = []
    for bubble in scene.layers.get("ui.speech_bubbles", []):
        if not isinstance(bubble, dict):
            continue
        visible_step = bubble.get("step", bubble.get("_step"))
        if visible_step is not None and not speech_step_is_visible(current_step, visible_step):
            continue
        if "_step" in bubble:
            try:
                bubble_step = int(bubble["_step"])
            except (TypeError, ValueError):
                bubble_step = current_step
            if current_step > bubble_step:
                continue
        bubbles.append(bubble)
    return bubbles


def draw_speech_bubbles(
    renderer: "Pygame_Renderer",
    scene: Any,
    entity_positions: dict[Entity, tuple[int, int]],
) -> None:
    """Draw speech bubbles above entities using rounded rects and tail polygons."""
    if scene.layers.get("ui.trade_sessions"):
        return
    speech_bubbles = collect_speech_bubbles(scene)
    if not speech_bubbles:
        return

    visible_bubbles: list[tuple[Entity, str, pygame.Rect, tuple[int, int]]] = []
    bubble_groups: dict[tuple[int, int], list[Entity]] = {}

    for bubble in speech_bubbles:
        if not isinstance(bubble, dict):
            continue
        entity = bubble.get("entity")
        text = str(bubble.get("text", "")).strip()
        if entity not in entity_positions or not text:
            continue

        px, py = entity_positions[entity]
        entity_rect = pygame_runtime(renderer).view.last_drawn_entity_rects.get(
            entity,
            pygame.Rect(px, py, renderer.tile_size, renderer.tile_size),
        )
        group_key = (
            (entity_rect.centerx - renderer.viewport_pad_w) // max(1, renderer.tile_size),
            (entity_rect.centery - renderer.viewport_pad_n) // max(1, renderer.tile_size),
        )
        visible_bubbles.append((entity, text, entity_rect, group_key))
        if entity not in bubble_groups.setdefault(group_key, []):
            bubble_groups[group_key].append(entity)

    for entity, text, entity_rect, group_key in visible_bubbles:
        renderable = renderable_component(entity)
        scale = getattr(renderable, "speech_bubble_scale", 1.0) if renderable is not None else 1.0

        group = bubble_groups[group_key]
        columns, rows = overlap_grid_dimensions(len(group))
        col, row, row_slots = centered_grid_slot(group.index(entity), len(group), columns)

        anchor_x = entity_rect.centerx
        anchor_y = entity_rect.top + max(4, min(renderer.tile_size // 6, entity_rect.height // 3))

        bubble_width = max(int(renderer.tile_size * 2.55), 140)
        bubble_height = max(int(renderer.tile_size * 1.18), 54)
        bubble_width = max(int(bubble_width * scale), int(140 * scale))
        bubble_height = max(int(bubble_height * scale), int(54 * scale))
        pad_left = max(int(10 * scale), int(renderer.tile_size * 0.18 * scale))
        pad_right = max(int(10 * scale), int(renderer.tile_size * 0.18 * scale))
        pad_top = max(int(8 * scale), int(renderer.tile_size * 0.14 * scale))
        pad_bottom = max(int(9 * scale), int(renderer.tile_size * 0.16 * scale))
        tail_width = max(int(14 * scale), int(renderer.tile_size * 0.5 * scale))
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
        horizontal_gap = max(8, renderer.tile_size // 6)
        horizontal_offset = int((col - (row_slots - 1) / 2) * (bubble_width + horizontal_gap))
        bubble_x = anchor_x - bubble_width // 2 + horizontal_offset
        world_width = renderer.effect_surface.get_width()
        if world_width > bubble_width + 12:
            bubble_x = max(6, min(bubble_x, world_width - bubble_width - 6))
        else:
            bubble_x = 6

        vertical_gap = max(6, renderer.tile_size // 10)
        vertical_offset = int((rows - 1 - row) * (bubble_height + tail_height + vertical_gap))
        bubble_y = max(6, anchor_y - bubble_height - tail_height - vertical_offset)
        content_left = bubble_x + pad_left
        content_top = bubble_y + pad_top
        content_width = bubble_width - pad_left - pad_right
        content_height = bubble_height - pad_top - pad_bottom

        bubble_rect = pygame.Rect(bubble_x, bubble_y, bubble_width, bubble_height)
        tail_base_x = max(
            bubble_rect.left + tail_width // 2,
            min(anchor_x, bubble_rect.right - tail_width // 2),
        )
        tail = [
            (tail_base_x - tail_width // 2, bubble_rect.bottom - 2),
            (tail_base_x + tail_width // 2, bubble_rect.bottom - 2),
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




def draw_trade_offers(
    renderer: "Pygame_Renderer",
    scene: Any,
    positions: dict[Entity, tuple[int, int]],
) -> None:
    """Draw trade windows from scene layer ``ui.trade_sessions``."""
    from .trading_rendering import draw_chat_session_window, draw_trade_session_window

    entity_lookup: dict[str, Entity] = {}
    for entity in positions:
        entity_lookup[entity.name] = entity
        for component in entity.components.values():
            # Trade offer items, inventory contents, containers
            for attr in ("items", "inventory", "contents"):
                for item in getattr(component, attr, []):
                    if isinstance(item, Entity):
                        entity_lookup[item.name] = item

    # ── Trade sessions (private negotiation, from extraction pipeline) ──
    sessions: list[dict] = scene.layers.get("ui.trade_sessions", [])
    for session in sessions:
        left_e = entity_lookup.get(session.get("left_name", ""))
        right_e = entity_lookup.get(session.get("right_name", ""))
        if left_e is None or right_e is None:
            continue
        left_pos = positions.get(left_e)
        right_pos = positions.get(right_e)
        if left_pos is None or right_pos is None:
            continue
        draw_trade_session_window(renderer, left_pos, right_pos, session, entity_lookup, 1.0)

    # ── Chat sessions (private conversation panel at the bottom) ──
    for chat in scene.layers.get("ui.chat_sessions", []):
        names = chat.get("participant_names", [])
        participant_positions = [
            positions[entity_lookup[name]]
            for name in names
            if name in entity_lookup and entity_lookup[name] in positions
        ]
        if not participant_positions:
            continue
        draw_chat_session_window(renderer, participant_positions, names, chat.get("messages", []), 1.0)


def auto_tiled_wall_sprites(
    renderer: "Pygame_Renderer",
    env: "Environment",
    renderables: list[tuple[int, Entity, Any]],
) -> dict[Entity, str]:
    """Resolve draw-time wall sprite overrides without mutating Renderable."""
    wall_positions: set[tuple[int, int]] = set()
    wall_entities: list[tuple[Entity, Any]] = []
    for _, entity, renderable in renderables:
        if renderable.wall_set is not None and "wall" in entity.tags:
            world_position = entity_world_position(renderer, env, entity)
            if world_position is None:
                continue
            wx, wy = world_position
            wall_positions.add((wx, wy))
            wall_entities.append((entity, renderable))

    resolved_sprites: dict[Entity, str] = {}
    for entity, renderable in wall_entities:
        world_position = entity_world_position(renderer, env, entity)
        if world_position is None:
            continue
        wx, wy = world_position
        neighbors = wall_neighbor_mask(wx, wy, wall_positions)
        resolved = resolve_wall_sprite(renderer, renderable.wall_set, neighbors)
        if resolved is not None:
            resolved_sprites[entity] = resolved
    return resolved_sprites



def render_environment(renderer: "Pygame_Renderer", env: "Environment", scene: Any | None = None) -> None:
    """Render a full frame including background, entities, effects, and HUD."""
    if scene is None:
        scene = renderer.extract_scene(env)
    update_damage_flash_state(renderer, env, scene)
    runtime = pygame_runtime(renderer)
    view = runtime.view
    renderables = scene.layers.get("world.renderables", [])
    background = scene.layers.get("world.background_tiles", [])
    if view.selected_entity is not None and selected_entity(env, renderer) is None:
        view.selected_entity = None
    if view.camera_focus_entity is not None and view.camera_focus_entity not in env.state.entities:
        view.camera_focus_entity = None
    min_world_x, max_world_x, min_world_y, max_world_y = world_bounds(renderer, env, background, renderables)
    full_grid_width = max(1, max_world_x - min_world_x + 1)
    full_grid_height = max(1, max_world_y - min_world_y + 1)
    min_x, max_x, min_y, max_y = update_camera_state(
        renderer,
        env,
        min_world_x=min_world_x,
        max_world_x=max_world_x,
        min_world_y=min_world_y,
        max_world_y=max_world_y,
    )

    view_grid_width = max(1, max_x - min_x + 1)
    view_grid_height = max(1, max_y - min_y + 1)
    grid_width = full_grid_width
    grid_height = full_grid_height
    sidebar = sidebar_state(scene)
    sidebar_lines = list(sidebar.get("lines", []))
    selected_action_lines = list(sidebar.get("selected_action", []))
    action_lines = list(sidebar.get("actions", []))
    needs_sidebar = bool(sidebar_lines or selected_action_lines or action_lines)
    sidebar_width_value = sidebar.get("width")
    requested_sidebar_width = int(sidebar_width_value or 380) if needs_sidebar else 0
    hud_visible = bool(scene_metadata(scene, "ui.hud_visible", True))
    resolved_tile_size = fitted_tile_size(
        renderer,
        grid_width=grid_width,
        grid_height=grid_height,
        sidebar_width=requested_sidebar_width,
        hud_visible=hud_visible,
    )
    if resolved_tile_size != renderer.tile_size:
        apply_renderer_metrics(renderer, resolved_tile_size)

    layout_tile_size = renderer.tile_size
    tile_area_width = grid_width * layout_tile_size
    tile_area_height = grid_height * layout_tile_size
    active_tile_size = layout_tile_size
    if view.camera_focus_entity is not None:
        focus_fit = min(
            tile_area_width // view_grid_width,
            tile_area_height // view_grid_height,
        )
        active_tile_size = min(256, max(layout_tile_size, focus_fit))
    view_offset_x = max(0, (tile_area_width - view_grid_width * active_tile_size) // 2)
    view_offset_y = max(0, (tile_area_height - view_grid_height * active_tile_size) // 2)

    sidebar_width = 0
    if needs_sidebar:
        sidebar_width = max(
            280,
            int(round(requested_sidebar_width * (renderer.tile_size / max(1, renderer.base_tile_size)))),
        )
    world_width = renderer.viewport_pad_w + renderer.viewport_pad_e + grid_width * renderer.tile_size
    hud_height = 0 if not hud_visible else renderer.hud_height
    world_height = renderer.viewport_pad_n + renderer.viewport_pad_s + grid_height * renderer.tile_size
    right_panel_width = max(renderer.terminal_width, sidebar_width)
    content_height = max(world_height, renderer.terminal_height)
    width = world_width + right_panel_width
    height = content_height + hud_height
    ensure_screen_size(renderer, width, height)

    renderer.screen.fill((8, 11, 16))
    renderer.floor_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.shadow_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.entity_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.effect_surface = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    renderer.world_surface = renderer.floor_surface
    renderer.floor_surface.fill((8, 11, 16))
    view.last_drawn_entity_rects = {}

    renderer.tile_size = active_tile_size
    try:
        visible_background = [
            item for item in background
            if is_within_visible_bounds(int(item["x"]), int(item["y"]), min_x, max_x, min_y, max_y)
        ]
        wall_positions = collect_wall_positions(visible_background)

        for item in visible_background:
            x = int(item["x"])
            y = int(item["y"])
            px, py = screen_rect_for_tile(renderer, x, y, min_x, max_y)
            px += view_offset_x
            py += view_offset_y
            draw_background_tile(renderer, item, px, py, wall_positions=wall_positions)

        wall_sprite_overrides = auto_tiled_wall_sprites(renderer, env, renderables)

        visible_entity_draws: list[tuple[Entity, Any, tuple[int, int], tuple[int, int]]] = []
        shared_tile_groups: dict[tuple[int, int], list[Entity]] = {}
        for _, entity, renderable in renderables:
            world_position = entity_world_position(renderer, env, entity)
            if world_position is None:
                continue
            x, y = world_position
            if not is_within_visible_bounds(x, y, min_x, max_x, min_y, max_y):
                continue
            position = interpolated_entity_screen_position(
                renderer,
                env,
                entity,
                min_x=min_x,
                max_y=max_y,
                offset_x=view_offset_x,
                offset_y=view_offset_y,
            )
            if position is None:
                continue
            visible_entity_draws.append((entity, renderable, world_position, position))
            if renderable.wall_set is None:
                shared_tile_groups.setdefault(world_position, []).append(entity)

        positions: dict[Entity, tuple[int, int]] = {}
        for entity, renderable, world_position, position in visible_entity_draws:
            px, py = position
            draw_rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
            group = shared_tile_groups.get(world_position, [])
            if renderable.wall_set is None and len(group) > 1:
                draw_rect = shared_tile_entity_rect(
                    renderer,
                    px,
                    py,
                    index=group.index(entity),
                    count=len(group),
                )
            positions[entity] = (draw_rect.x, draw_rect.y)
            draw_entity(
                renderer,
                entity,
                renderable,
                draw_rect.x,
                draw_rect.y,
                draw_size=draw_rect.width,
                sprite_name_override=wall_sprite_overrides.get(entity),
            )

        draw_hit_effects(renderer, scene, positions)
        draw_speech_bubbles(renderer, scene, positions)
        draw_trade_offers(renderer, scene, positions)
        draw_selected_entity_card(renderer, env, positions)
    finally:
        renderer.tile_size = layout_tile_size

    world_x = 0
    right_panel_x = world_x + world_width
    renderer.screen.blit(renderer.floor_surface, (world_x, 0))
    renderer.screen.blit(renderer.shadow_surface, (world_x, 0))
    renderer.screen.blit(renderer.entity_surface, (world_x, 0))
    renderer.screen.blit(renderer.effect_surface, (world_x, 0))
    draw_world_vignette(renderer, world_x, world_width, world_height)

    draw_text_terminal_panel(
        renderer,
        x_offset=right_panel_x,
        y_offset=0,
        width=right_panel_width,
        height=height,
    )
    draw_hud_panel(renderer, scene, world_x, world_width, height)
    draw_end_overlay(renderer, scene, world_x, world_width, world_height)
    pygame.display.flip()
