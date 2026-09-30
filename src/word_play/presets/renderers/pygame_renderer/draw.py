from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity
from word_play.presets.systems.inventory import Inventory

from .assets import (
    animation_sibling,
    back_sibling,
    get_or_load_image,
    get_scaled_image,
    get_soft_shadow,
    resolve_wall_sprite,
)
from ..themes import apply_theme_defaults, placeholder, resolve_sprite
from .chrome import active_chrome
from .fonts import render_text, wrap_text_lines
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
            # Float camera: ease the center toward the focus entity so the view
            # pans in sub-tile pixels instead of lurching a whole tile whenever
            # the entity crosses a tile boundary (Keren, "Scroll Back").
            now = time.monotonic()
            dt = min(0.1, max(0.0, now - view.camera_pan_time)) if view.camera_pan_time else 0.0
            view.camera_pan_time = now
            target = (float(focus_x), float(focus_y))
            center = view.camera_center
            if center is None or abs(center[0] - target[0]) + abs(center[1] - target[1]) > radius * 2 + 4:
                center = target                          # first frame / teleport: snap
            else:
                ease = 1.0 - math.exp(-dt * 4.5)
                center = (
                    center[0] + (target[0] - center[0]) * ease,
                    center[1] + (target[1] - center[1]) * ease,
                )
            view.camera_center = center
            min_x, max_x, frac_x = _float_camera_axis(center[0], radius, min_world_x, max_world_x)
            min_y, max_y, frac_y = _float_camera_axis(center[1], radius, min_world_y, max_world_y)
            view.camera_frac = (frac_x, frac_y)
            return min_x, max_x, min_y, max_y

    effects.camera_shake_strength = 0.0 if effects.camera_shake_until <= time.monotonic() else effects.camera_shake_strength
    view.camera_center = None
    view.camera_pan_time = 0.0
    view.camera_frac = (0.0, 0.0)
    return min_world_x, max_world_x, min_world_y, max_world_y


def _float_camera_axis(center: float, radius: int, min_world: int, max_world: int) -> tuple[int, int, float]:
    """One axis of the float camera: integer tile window + fractional origin.

    The window keeps its nominal size (layout stays stable); the fractional
    part becomes a sub-tile pixel pan applied at composite time.
    """
    size = radius * 2 + 1
    world_size = max_world - min_world + 1
    if world_size <= size:
        return min_world, max_world, 0.0

    center = max(min_world + radius, min(max_world - radius, center))
    origin = center - radius
    min_bound = math.floor(origin)
    frac = origin - min_bound
    return int(min_bound), int(min_bound) + size - 1, frac


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


def _smoothstep(progress: float) -> float:
    """Ease-in/out for hops that begin at rest: soft start, soft landing."""
    return progress * progress * (3.0 - 2.0 * progress)


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
    """Entity screen position, gliding smoothly toward its tile when enabled.

    Glide state lives in world TILE coordinates (not screen pixels), so a
    panning or zooming camera never disturbs an in-flight traverse.
    """
    world_position = entity_world_position(renderer, env, entity)
    if world_position is None:
        return None

    def to_screen(tile_x: float, tile_y: float) -> tuple[int, int]:
        px = renderer.viewport_pad_w + (tile_x - min_x) * renderer.tile_size + offset_x
        py = renderer.viewport_pad_n + (max_y - tile_y) * renderer.tile_size + offset_y
        return int(round(px)), int(round(py))

    target_x, target_y = float(world_position[0]), float(world_position[1])

    config = renderer.beautify
    if not config.enabled or not config.smooth_movement:
        return to_screen(target_x, target_y)

    view = pygame_runtime(renderer).view
    now = time.monotonic()
    prev = view.entity_glide.get(entity)
    if prev is None:
        view.entity_glide[entity] = (target_x, target_y, target_x, target_y, now, 0.0, False)
        view.entities_in_motion.discard(entity)
        return to_screen(target_x, target_y)

    start_x, start_y, tx, ty, t0, duration, ease = prev
    progress = 1.0 if duration <= 0 else min(1.0, max(0.0, (now - t0) / duration))
    curved = _smoothstep(progress) if ease else progress
    shown_x = start_x + (tx - start_x) * curved
    shown_y = start_y + (ty - start_y) * curved

    if (tx, ty) != (target_x, target_y):
        # New target: learn the sim-step cadence (EMA) and start a traverse that
        # spans ~90% of it — constant velocity, walking the whole interval
        # instead of dashing and freezing.
        interval = now - view.glide_last_change
        if 0.05 < interval < 5.0:
            view.glide_interval_ema = 0.6 * view.glide_interval_ema + 0.4 * interval
            view.glide_last_change = now
        elif view.glide_last_change == 0.0:
            view.glide_last_change = now
        was_resting = progress >= 1.0
        delay = 0.0
        if abs(target_x - shown_x) + abs(target_y - shown_y) > 3.2:
            shown_x, shown_y = target_x, target_y      # teleport: snap
            duration = 0.0
            ease = False
        else:
            # A lockstep sim step would otherwise read as one synchronized
            # hop. Each entity waits out its own stable slice of the interval
            # before walking (de-synced crowd), and a hop that begins at rest
            # eases in and out instead of snapping to full speed.
            span = view.glide_interval_ema * 0.9
            delay = ((id(entity) >> 4) % 977) / 977.0 * 0.25 * span
            duration = min(2.5, max(0.18, span - delay))
            ease = was_resting
        dx, dy = target_x - shown_x, target_y - shown_y
        if abs(dx) >= abs(dy) and abs(dx) > 0.02:
            view.entity_facing[entity] = "right" if dx > 0 else "left"
        elif abs(dy) > 0.02:
            # world-y grows northward: walking up-screen means walking away
            view.entity_facing[entity] = "up" if dy > 0 else "down"
        view.entity_glide[entity] = (shown_x, shown_y, target_x, target_y, now + delay, duration, ease)
        progress = 0.0 if duration else 1.0

    if progress >= 1.0:
        view.entities_in_motion.discard(entity)
        shown_x, shown_y = target_x, target_y
    else:
        view.entities_in_motion.add(entity)
    return to_screen(shown_x, shown_y)


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
    pygame.draw.rect(renderer.effect_surface, active_chrome(renderer).focus, ring_rect, width=3, border_radius=10)


def draw_selection_ring(renderer: "Pygame_Renderer", entity: Entity, px: int, py: int, size: int | None = None) -> None:
    """Highlight the selected entity so inspection is visually anchored."""
    if pygame_runtime(renderer).view.selected_entity is not entity:
        return
    entity_size = renderer.tile_size if size is None else size
    ring_rect = pygame.Rect(px - 7, py - 7, entity_size + 14, entity_size + 14)
    glow = pygame.Surface((ring_rect.width + 12, ring_rect.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (*active_chrome(renderer).selection, 58), glow.get_rect(), width=8, border_radius=16)
    renderer.effect_surface.blit(glow, (ring_rect.x - 6, ring_rect.y - 6))
    pygame.draw.rect(renderer.effect_surface, active_chrome(renderer).selection, ring_rect, width=3, border_radius=12)


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
    chrome = active_chrome(renderer)
    title_font = renderer.hud_font
    body_font = renderer.small_font
    metrics = selected_card_metrics(renderer, stat_count=len(stats), inventory_line_count=min(4, len(inventory_entries)))
    name_surface = render_text(title_font, inspected.name, chrome.text_on_card)
    subtitle = "Agent" if inspected.is_agent else "Entity"
    subtitle_surface = render_text(body_font, subtitle, chrome.accent_deep)

    stat_surfaces = []
    label_color = chrome.accent_deep
    value_color = chrome.text_on_card
    for label, value in stats:
        stat_surfaces.append(
            (
                render_text(body_font, f"{label}:", label_color),
                render_text(body_font, str(value), value_color),
            )
        )
    inventory_header_surface = render_text(body_font, "Inventory:", chrome.accent_deep) if inventory_entries else None
    inventory_item_surfaces = []
    for entry in inventory_entries[:4]:
        item_name = str(entry.get("name", "Item"))
        item_count = int(entry.get("count", 0))
        line = f"- {item_name} x{item_count}" if item_count > 1 else f"- {item_name}"
        inventory_item_surfaces.append(render_text(body_font, line, chrome.text_on_card_soft))

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

    tail_anchor_x = entity_rect.centerx
    tail_anchor_x = max(card_rect.left + 24, min(tail_anchor_x, card_rect.right - 24))
    tail = [
        (tail_anchor_x - 12, card_rect.bottom - 2),
        (tail_anchor_x + 12, card_rect.bottom - 2),
        (entity_rect.centerx, entity_rect.top - 8),
    ]
    pygame.draw.polygon(renderer.effect_surface, chrome.card, tail)
    pygame.draw.polygon(renderer.effect_surface, chrome.card_edge, tail, width=2)
    chrome.draw_card(renderer.effect_surface, card_rect, radius=metrics["corner_radius"])

    portrait_rect = pygame.Rect(
        card_rect.x + metrics["outer_pad"],
        card_rect.y + metrics["outer_pad"],
        portrait_size,
        portrait_size,
    )
    pygame.draw.rect(renderer.effect_surface, chrome.panel, portrait_rect, border_radius=14)
    pygame.draw.rect(renderer.effect_surface, chrome.panel_edge_hi, portrait_rect, width=1, border_radius=14)

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
        image = get_scaled_image(renderer, placeholder(sprite_name, "blit"), width, height)

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
        sprite_name = placeholder(wall_set, "wall set")
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
        rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
        pygame.draw.rect(renderer.floor_surface, (40, 50, 60), rect)
        placeholder(f"wall tile at ({item.get('x')}, {item.get('y')})", "missing wall_set")
        return True

    wall_set = str(wall_set)
    # bare role names ("wall") resolve through the active theme
    if "/" not in wall_set:
        resolved_set = None if renderer.theme is None else renderer.theme.wall_set(wall_set)
        if resolved_set is not None:
            wall_set = resolved_set

    neighbors = wall_neighbor_mask(int(item["x"]), int(item["y"]), wall_positions)
    return draw_wall_sprite(renderer, wall_set, px, py, neighbors)


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


def animated_sprite_name(
    renderer: "Pygame_Renderer",
    sprite_name: str,
    *,
    stagger: int = 0,
    fast: bool = False,
) -> str:
    """Swap in the '_2' frame on alternating ticks when a sibling exists.

    ``fast`` (used while an entity glides between tiles) more than doubles the
    frame rate, which reads as a walk cycle.
    """
    config = renderer.beautify
    if not config.enabled or not config.animate:
        return sprite_name
    lowered = sprite_name.lower()
    if any(fragment in lowered for fragment in config.animate_skip_fragments):
        return sprite_name
    sibling = animation_sibling(renderer, sprite_name)
    if sibling is None:
        return sprite_name
    period = max(0.05, config.animation_period / (2.5 if fast else 1.0))
    tick = int(time.monotonic() / period)
    return sibling if (tick + stagger) % 2 else sprite_name


def _shares_tile(renderable: Renderable) -> bool:
    """Walls and floor terrain never crowd a tile; everything else is offset
    side-by-side when several entities stand on the same tile."""
    return renderable.wall_set is None and not renderable.floor


def sprite_draw_height(renderer: "Pygame_Renderer", image: Any, width: int) -> int:
    """Aspect-preserving height: a 16x32 sprite draws one tile wide and two tall,
    anchored at the bottom of its tile — tall trees/props need no extra API."""
    if renderer.beautify.enabled and image.get_width() > 0:
        ratio = image.get_height() / image.get_width()
        if ratio > 1.2:
            return int(width * ratio)
    return width


def draw_entity(
    renderer: "Pygame_Renderer",
    entity: Entity,
    renderable: Renderable,
    px: int,
    py: int,
    *,
    draw_size: int | None = None,
    sprite_name_override: str | None = None,
) -> None:
    """Draw an entity sprite, including damage flash and optional overlay."""
    sprite_size = draw_size or renderer.tile_size
    # resolve a bare name to its file first: the _back/_2 sibling
    # conventions below work on real paths
    sprite_name = resolve_sprite(renderer.theme, sprite_name_override or renderable.sprite_path)
    view = pygame_runtime(renderer).view
    in_motion = entity in view.entities_in_motion
    facing = view.entity_facing.get(entity, "down")
    if facing == "up":
        rear = back_sibling(renderer, sprite_name)
        if rear is not None:
            sprite_name = rear
    sprite_name = animated_sprite_name(renderer, sprite_name, stagger=id(entity) >> 6, fast=in_motion)
    image = get_or_load_image(renderer, sprite_name)
    if image is None:
        sprite_name = placeholder(sprite_name, f"entity '{entity.name}'")
        image = get_or_load_image(renderer, sprite_name)
    draw_height = sprite_draw_height(renderer, image, sprite_size)
    scaled_image = get_scaled_image(renderer, sprite_name, sprite_size, draw_height)
    if facing == "left" and renderable.wall_set is None:
        cache = pygame_runtime(renderer).session.scaled_image_cache
        unflipped = scaled_image
        scaled_image = cache.get_or_build(
            (sprite_name, sprite_size, draw_height, -1), lambda: pygame.transform.flip(unflipped, True, False)
        )
    # team/ownership recolor: multiply toward the tint hue (keeps the ink
    # outline dark, unlike an additive flash) — cached per sprite state
    tint = renderable.tint
    if tint is not None:
        tint_strength = max(0.0, min(1.0, renderable.tint_strength))
        if tint_strength > 0.0:
            untinted = scaled_image

            def build_tinted() -> Any:
                tinted = untinted.copy()
                mult = tuple(int(255 - tint_strength * (255 - int(c))) for c in tint)
                tinted.fill((*mult, 255), special_flags=pygame.BLEND_RGB_MULT)
                return tinted

            cache = pygame_runtime(renderer).session.scaled_image_cache
            tint_key = (
                "__tint__", sprite_name, sprite_size, draw_height,
                facing == "left", tuple(tint), round(tint_strength, 2),
            )
            scaled_image = cache.get_or_build(tint_key, build_tinted)
    flash_until = pygame_runtime(renderer).effects.damage_flash_until.get(entity, 0.0)
    if flash_until > time.monotonic():
        scaled_image = flash_tinted_surface(scaled_image, tint=(190, 20, 20), alpha=140)
    is_wall = renderable.wall_set is not None
    is_floor = renderable.floor
    if not is_wall and not is_floor:
        soft_shadow = get_soft_shadow(renderer, sprite_name, sprite_size)
        if soft_shadow is not None:
            shadow_width, shadow_height = soft_shadow.get_size()
            shadow = soft_shadow
        else:
            shadow_width = max(14, int(sprite_size * 0.72))
            shadow_height = max(8, int(sprite_size * 0.24))
            shadow = pygame.Surface((shadow_width, shadow_height), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 72), shadow.get_rect())
        shadow_x = px + (sprite_size - shadow_width) // 2
        shadow_y = py + sprite_size - shadow_height // 2 - max(2, sprite_size // 12)
        renderer.shadow_surface.blit(shadow, (shadow_x, shadow_y))
    draw_py = py - (draw_height - sprite_size)          # bottom-anchor tall sprites
    if is_floor:
        # Walk-on terrain (docks, bridges, rugs): paint into the ground layer so
        # entities render on top of it, and skip shadow/rings/click-registration —
        # a floor tile is scenery an agent stands on, not a selectable entity.
        renderer.floor_surface.blit(scaled_image, (px, draw_py))
        return
    renderer.entity_surface.blit(scaled_image, (px, draw_py))
    pygame_runtime(renderer).view.last_drawn_entity_rects[entity] = pygame.Rect(px, draw_py, sprite_size, draw_height)
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
        sprite_name = placeholder(f"{kind} tile at ({item.get('x')}, {item.get('y')})", "missing sprite")
    else:
        sprite_name = resolve_sprite(renderer.theme, str(sprite_name))

    # animation frame swap, staggered by position
    tile_x, tile_y = int(item.get("x", 0)), int(item.get("y", 0))
    sprite_name = animated_sprite_name(renderer, sprite_name, stagger=tile_x + tile_y)
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

    chrome = active_chrome(renderer)
    hud_top = height - renderer.hud_height
    panel_rect = pygame.Rect(x_offset, hud_top, width, renderer.hud_height)
    chrome.draw_panel(renderer.screen, panel_rect, edge_top=True)

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

    header = render_text(renderer.hud_font, str(header_text), chrome.text_on_panel)
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
        controls = render_text(renderer.small_font, line, chrome.text_on_panel_dim)
        renderer.screen.blit(controls, (x_offset + renderer.margin, hud_top + 48 + line_index * renderer.small_font.get_linesize()))

def draw_end_overlay(renderer: "Pygame_Renderer", scene: Any, world_x: int, world_width: int, world_height: int) -> None:
    """Draw a centered overlay when the environment reaches a terminal state."""
    overlay_state = scene_metadata(scene, "ui.completion_overlay", {})
    if not isinstance(overlay_state, dict) or not bool(overlay_state.get("visible", False)):
        return

    chrome = active_chrome(renderer)
    title = str(overlay_state.get("title", "Experiment Completed"))
    subtitle = str(overlay_state.get("subtitle", "The scheduled run has finished."))
    accent = chrome.text_on_card_soft

    overlay = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    overlay.fill((*chrome.backdrop, 170))
    renderer.screen.blit(overlay, (world_x, 0))

    # Calculate text dimensions with wrapping support
    title_surface = render_text(renderer.font, title, chrome.text_on_card)

    # Wrap subtitle text to fit within max width
    max_text_width = min(480, world_width - 80)
    subtitle_lines = wrap_text_lines(renderer.hud_font, subtitle, max_width=max_text_width)
    subtitle_surfaces = [render_text(renderer.hud_font, line, accent) for line in subtitle_lines]
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
    chrome.draw_card(renderer.screen, panel_rect, radius=18)

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
    chrome = active_chrome(renderer)
    prompt = pygame_runtime(renderer).prompt
    panel_rect = pygame.Rect(x_offset, y_offset, width, height)
    prompt.panel_rect = panel_rect

    pygame.draw.rect(renderer.screen, chrome.term_bg, panel_rect)
    pygame.draw.line(renderer.screen, chrome.term_edge, (x_offset, y_offset), (x_offset, y_offset + height), 2)
    pygame.draw.line(renderer.screen, chrome.term_edge_soft, (x_offset, y_offset), (x_offset + width, y_offset), 2)

    pad_x = 18
    pad_y = 14
    title_text = prompt.title if prompt.active else "Terminal"
    subtitle_text = "human input active" if prompt.active else "latest human testing output"
    title_surface = render_text(renderer.hud_font, title_text, chrome.term_text)
    subtitle_surface = render_text(renderer.small_font, subtitle_text, chrome.term_text_dim)
    renderer.screen.blit(title_surface, (panel_rect.x + pad_x, panel_rect.y + pad_y))
    renderer.screen.blit(
        subtitle_surface,
        (panel_rect.x + pad_x + title_surface.get_width() + 16, panel_rect.y + pad_y + 4),
    )

    footer_text = "Mouse wheel / PgUp / PgDn scroll | Enter submit | Esc cancel"
    footer_surface = render_text(renderer.small_font, footer_text, chrome.term_text_soft)
    footer_y = panel_rect.bottom - footer_surface.get_height() - 8
    renderer.screen.blit(footer_surface, (panel_rect.x + pad_x, footer_y))

    input_height = max(42, renderer.hud_font.get_linesize() + 18)
    input_rect = pygame.Rect(
        panel_rect.x + pad_x,
        footer_y - input_height - 10,
        panel_rect.width - pad_x * 2,
        input_height,
    )
    pygame.draw.rect(renderer.screen, chrome.term_input_bg, input_rect, border_radius=10)
    pygame.draw.rect(renderer.screen, chrome.term_input_edge, input_rect, width=2, border_radius=10)

    prefix_text = prompt.prompt if prompt.active else "> "
    prefix_surface = render_text(renderer.hud_font, prefix_text, chrome.term_text)
    prefix_x = input_rect.x + 12
    prefix_y = input_rect.y + (input_rect.height - prefix_surface.get_height()) // 2
    renderer.screen.blit(prefix_surface, (prefix_x, prefix_y))

    if prompt.active:
        cursor = "_" if int(time.monotonic() * 2) % 2 == 0 else " "
        input_text = prompt.input_text + cursor
        input_color = chrome.term_input_text
    else:
        input_text = "Waiting for the next human prompt..."
        input_color = chrome.term_text_faint
    max_input_width = input_rect.width - 24 - prefix_surface.get_width()
    visible_text = input_text
    while visible_text and renderer.hud_font.size(visible_text)[0] > max_input_width:
        visible_text = visible_text[1:]
    input_surface = render_text(renderer.hud_font, visible_text, input_color)
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
    pygame.draw.rect(renderer.screen, chrome.term_inset, transcript_rect, border_radius=10)
    pygame.draw.rect(renderer.screen, chrome.term_inset_edge, transcript_rect, width=1, border_radius=10)

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
            surface = render_text(renderer.small_font, line, chrome.term_transcript_text)
            renderer.screen.blit(surface, (transcript_rect.x + 10, line_y))
        line_y += line_height

    if max_offset > 0:
        track_rect = pygame.Rect(transcript_rect.right - 10, transcript_rect.y + 8, 4, transcript_rect.height - 16)
        pygame.draw.rect(renderer.screen, chrome.term_track, track_rect, border_radius=4)
        thumb_height = max(18, int(track_rect.height * (visible_line_count / max(1, len(transcript_lines)))))
        scroll_ratio = start_index / max(1, max_offset)
        thumb_y = track_rect.y + int((track_rect.height - thumb_height) * scroll_ratio)
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
        pygame.draw.rect(renderer.screen, chrome.term_thumb, thumb_rect, border_radius=4)


def draw_world_vignette(renderer: "Pygame_Renderer", world_x: int, world_width: int, world_height: int) -> None:
    """Apply a subtle darkening toward the edges of the world view."""
    cache_key = (world_width, world_height)
    session = pygame_runtime(renderer).session
    overlay = session.overlay_cache.get(cache_key)
    if overlay is None:
        # Build the radial falloff at low resolution and smoothscale up: the
        # gradient is low-frequency, so this reads identically to a per-pixel
        # build while avoiding ~1.5M Python set_at calls on first frame/resize.
        low_w = max(2, min(160, world_width))
        low_h = max(2, min(160, int(round(low_w * world_height / max(1, world_width)))))
        field = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
        center_x = low_w / 2
        center_y = low_h / 2
        max_distance = math.hypot(center_x, center_y) or 1.0
        for y in range(low_h):
            for x in range(low_w):
                distance = math.hypot(x - center_x, y - center_y)
                alpha = int(max(0.0, min(78.0, ((distance / max_distance) ** 1.9) * 78.0)))
                field.set_at((x, y), (6, 8, 12, alpha))
        overlay = pygame.transform.smoothscale(field, (world_width, world_height))
        session.overlay_cache[cache_key] = overlay
    renderer.screen.blit(overlay, (world_x, 0))


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
    speech_bubbles = collect_speech_bubbles(scene)
    if not speech_bubbles:
        return

    chrome = active_chrome(renderer)
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
        text_surfaces = [render_text(speech_font, line, chrome.bubble_text) for line in lines]
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
        pygame.draw.rect(renderer.effect_surface, chrome.bubble_fill, bubble_rect, border_radius=radius)
        pygame.draw.rect(renderer.effect_surface, chrome.bubble_edge, bubble_rect, width=2, border_radius=radius)
        pygame.draw.polygon(renderer.effect_surface, chrome.bubble_fill, tail)
        pygame.draw.polygon(renderer.effect_surface, chrome.bubble_edge, tail, width=2)

        text_y = content_top + max(0, (content_height - text_height) // 2)
        for surface in text_surfaces:
            text_x = content_left + max(0, (content_width - surface.get_width()) // 2)
            renderer.effect_surface.blit(surface, (text_x, text_y))
            text_y += surface.get_height() + line_gap



def auto_tiled_wall_sprites(
    renderer: "Pygame_Renderer",
    env: "Environment",
    renderables: list[tuple[int, Entity, Any]],
) -> dict[Entity, str]:
    """Resolve draw-time wall sprite overrides without mutating Renderable.

    Walls essentially never move, so the resolved mapping is cached and reused
    until any wall entity, position, or set changes.
    """
    session = pygame_runtime(renderer).session
    wall_positions: set[tuple[int, int]] = set()
    wall_entities: list[tuple[Entity, Any, tuple[int, int]]] = []
    for _, entity, renderable in renderables:
        if renderable.wall_set is not None and "wall" in entity.tags:
            world_position = entity_world_position(renderer, env, entity)
            if world_position is None:
                continue
            wall_positions.add(world_position)
            wall_entities.append((entity, renderable, world_position))

    cache_key = tuple((id(entity), renderable.wall_set, position) for entity, renderable, position in wall_entities)
    if cache_key == session.wall_override_key:
        return session.wall_override_result

    resolved_sprites: dict[Entity, str] = {}
    for entity, renderable, (wx, wy) in wall_entities:
        neighbors = wall_neighbor_mask(wx, wy, wall_positions)
        resolved = resolve_wall_sprite(renderer, renderable.wall_set, neighbors)
        if resolved is not None:
            resolved_sprites[entity] = resolved
    session.wall_override_key = cache_key
    session.wall_override_result = resolved_sprites
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
    theme = renderer.theme
    for _, _, renderable in renderables:
        apply_theme_defaults(renderable, theme)
    if view.selected_entity is not None and selected_entity(env, renderer) is None:
        view.selected_entity = None
    if view.camera_focus_entity is not None and view.camera_focus_entity not in env.state.entities:
        view.camera_focus_entity = None
    if view.entity_glide:
        live = set(env.state.entities)
        for stale in [e for e in view.entity_glide if e not in live]:
            del view.entity_glide[stale]
            view.entities_in_motion.discard(stale)
            view.entity_facing.pop(stale, None)

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

    # Float camera: the fractional window origin becomes a sub-tile pixel pan.
    # Layout stays on the integer window; culling widens by one tile on the max
    # side to fill the strip the pan reveals; a clip keeps it inside the view box.
    frac_x, frac_y = view.camera_frac
    camera_clip: pygame.Rect | None = None
    if view.camera_focus_entity is not None:
        camera_clip = pygame.Rect(
            renderer.viewport_pad_w + view_offset_x,
            renderer.viewport_pad_n + view_offset_y,
            view_grid_width * active_tile_size,
            view_grid_height * active_tile_size,
        )
    cull_max_x = max_x + (1 if frac_x > 1e-6 else 0)
    cull_max_y = max_y + (1 if frac_y > 1e-6 else 0)
    view_offset_x -= int(round(frac_x * active_tile_size))
    view_offset_y += int(round(frac_y * active_tile_size))

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

    chrome = active_chrome(renderer)
    renderer.screen.fill(chrome.backdrop)
    # Layer surfaces persist across frames (cleared, not reallocated): four
    # full-screen SRCALPHA allocations per frame were the largest source of
    # allocator churn and frame-time spikes.
    session = runtime.session
    layer_size = (world_width, world_height)
    if session.layer_size != layer_size:
        session.layer_size = layer_size
        session.layer_surfaces = {
            name: pygame.Surface(layer_size, pygame.SRCALPHA)
            for name in ("floor", "shadow", "entity", "effect")
        }
    renderer.floor_surface = session.layer_surfaces["floor"]
    renderer.shadow_surface = session.layer_surfaces["shadow"]
    renderer.entity_surface = session.layer_surfaces["entity"]
    renderer.effect_surface = session.layer_surfaces["effect"]
    renderer.world_surface = renderer.floor_surface
    # clear any clip left from a previous focus-mode frame BEFORE filling
    for surface in (renderer.floor_surface, renderer.shadow_surface, renderer.entity_surface, renderer.effect_surface):
        surface.set_clip(None)
    renderer.floor_surface.fill(chrome.backdrop)
    renderer.shadow_surface.fill((0, 0, 0, 0))
    renderer.entity_surface.fill((0, 0, 0, 0))
    renderer.effect_surface.fill((0, 0, 0, 0))
    view.last_drawn_entity_rects = {}
    if camera_clip is not None:
        for surface in (renderer.floor_surface, renderer.shadow_surface, renderer.entity_surface, renderer.effect_surface):
            surface.set_clip(camera_clip)

    renderer.tile_size = active_tile_size
    try:
        visible_background = [
            item for item in background
            if is_within_visible_bounds(int(item["x"]), int(item["y"]), min_x, cull_max_x, min_y, cull_max_y)
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
            # the focused entity is never culled: its glide may trail the eased
            # camera window by more than the margin right after a multi-tile hop
            if entity is not view.camera_focus_entity and not is_within_visible_bounds(
                x, y, min_x, cull_max_x, min_y, cull_max_y
            ):
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
            # floor tiles (docks, rugs, bridges) are terrain an agent stands ON,
            # so they never join the shared-tile group — the agent draws centered
            # on top instead of being offset side-by-side with the floor.
            if _shares_tile(renderable):
                shared_tile_groups.setdefault(world_position, []).append(entity)

        positions: dict[Entity, tuple[int, int]] = {}
        for entity, renderable, world_position, position in visible_entity_draws:
            px, py = position
            draw_rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
            group = shared_tile_groups.get(world_position, [])
            if _shares_tile(renderable) and len(group) > 1:
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

        # UI overlays (speech bubbles, inspector card, hit effects)
        # intentionally rise into the viewport padding; the cull-margin clip
        # must not cut them. World-tied content above keeps the clip.
        renderer.effect_surface.set_clip(None)
        draw_hit_effects(renderer, scene, positions)
        draw_speech_bubbles(renderer, scene, positions)
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
