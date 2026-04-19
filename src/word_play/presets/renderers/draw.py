from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Any

import pygame

from word_play.core import Entity

from .assets import get_or_load_image, get_scaled_image, resolve_wall_sprite
from .wall_geometry import collect_wall_positions, normalize_background_item, screen_position_for_entity, screen_rect_for_tile, wall_neighbor_mask, world_bounds
from .renderer import Renderable
from .runtime import apply_renderer_metrics, ensure_screen_size, fitted_tile_size

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import Pygame_Renderer


def visible_renderables(env: "Environment") -> list[tuple[int, Entity, Renderable]]:
    """Collect visible renderable entities sorted by their draw order."""
    renderables: list[tuple[int, Entity, Renderable]] = []
    for entity in env.state.entities:
        renderable = entity.get_component(Renderable)
        if renderable is not None and renderable.visible:
            renderables.append((renderable.z_index, entity, renderable))
    renderables.sort(key=lambda item: item[0])
    return renderables


def background_items(env: "Environment", renderer: "Pygame_Renderer") -> list[dict[str, Any]]:
    """Fetch and normalize background tiles from the active layout adapter."""
    return [normalize_background_item(item) for item in renderer.layout.background(env)]


def world_positions(
    renderer: "Pygame_Renderer",
    background: list[dict[str, Any]],
    renderables: list[tuple[int, Entity, Renderable]],
) -> list[tuple[int, int]]:
    """Collect all world-space tile positions contributing to the visible map."""
    positions: list[tuple[int, int]] = []
    for item in background:
        positions.append((int(item["x"]), int(item["y"])))
    for _, entity, _ in renderables:
        try:
            x, y = renderer.layout.screen_position(entity.position)
        except AttributeError:
            continue
        positions.append((int(x), int(y)))
    return positions


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


def entity_inventory_items(entity: Entity) -> list[str]:
    """Return display names for any inventory-like component contents."""
    for component in entity.components.values():
        inventory = getattr(component, "inventory", None)
        if isinstance(inventory, list):
            return [getattr(item, "name", str(item)) for item in inventory]
        if isinstance(inventory, dict):
            return [f"{name} x{int(count)}" for name, count in inventory.items() if int(count) > 0]
    return []


def title_case_name(raw: str) -> str:
    """Convert snake/camel-ish names into short label text."""
    return raw.replace("_", " ").strip().title()


def compact_dict_text(values: dict[Any, Any], *, limit: int = 3) -> str:
    """Render a compact summary for a small mapping."""
    parts: list[str] = []
    for index, (key, value) in enumerate(values.items()):
        if index >= limit:
            break
        parts.append(f"{str(key)[:3]}:{value}")
    if len(values) > limit:
        parts.append("...")
    return " ".join(parts)


STATUS_COMPONENT_FIELDS = ("health", "money")


def entity_inventory_entries(entity: Entity, env: "Environment" | None = None) -> list[dict[str, Any]]:
    """Return inventory entries with names, counts, and sprite hints for the inspector card."""
    sprite_map = dict(getattr(env, "inventory_sprite_map", {})) if env is not None else {}
    entries: list[dict[str, Any]] = []

    for component in entity.components.values():
        inventory = getattr(component, "inventory", None)
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
    """Derive only approved quantifiable status stats from the entity state."""
    stats: list[tuple[str, str]] = []

    if "health" in STATUS_COMPONENT_FIELDS:
        health = entity_health_value(entity)
        max_health = entity_max_health_value(entity)
        if health is not None and max_health is not None:
            stats.append(("HP", f"{int(health)}/{int(max_health)}"))
        elif health is not None:
            stats.append(("HP", f"{int(health)}"))

    if "money" in STATUS_COMPONENT_FIELDS:
        for component in entity.components.values():
            if hasattr(component, "money"):
                stats.append(("Money", str(int(getattr(component, "money")))))
                break

    return stats


def entity_status_lines(entity: Entity) -> list[str]:
    """Summarize useful entity details for the inspector sidebar."""
    lines = [f"Name: {entity.name}"]
    lines.append(f"Role: {'Agent' if entity.is_agent else 'Entity'}")
    lines.append(f"Position: ({entity.position.x}, {entity.position.y})")

    health = entity_health_value(entity)
    max_health = entity_max_health_value(entity)
    if health is not None and max_health is not None:
        lines.append(f"Health: {int(health)}/{int(max_health)}")
    elif health is not None:
        lines.append(f"Health: {int(health)}")

    inventory_items = entity_inventory_items(entity)
    if inventory_items:
        lines.append(f"Inventory: {', '.join(inventory_items[:3])}")
        if len(inventory_items) > 3:
            lines.append(f"Inventory+: {len(inventory_items) - 3} more")

    visible_tags = [tag for tag in entity.tags if tag not in {"in_inventory"}]
    if visible_tags:
        lines.append(f"Tags: {', '.join(visible_tags[:4])}")
        if len(visible_tags) > 4:
            lines.append(f"Tags+: {len(visible_tags) - 4} more")

    component_names = [type(component).__name__.replace("_", " ") for component in entity.components.values()]
    if component_names:
        lines.append(f"Components: {', '.join(component_names[:3])}")
        if len(component_names) > 3:
            lines.append(f"Components+: {len(component_names) - 3} more")

    return lines


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


def draw_entity_shadow(renderer: "Pygame_Renderer", px: int, py: int) -> None:
    """Draw a soft ground shadow to give actors and props more depth."""
    shadow_width = max(14, int(renderer.tile_size * 0.72))
    shadow_height = max(8, int(renderer.tile_size * 0.24))
    shadow = pygame.Surface((shadow_width, shadow_height), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 72), shadow.get_rect())
    shadow_x = px + (renderer.tile_size - shadow_width) // 2
    shadow_y = py + renderer.tile_size - shadow_height // 2 - max(2, renderer.tile_size // 12)
    renderer.shadow_surface.blit(shadow, (shadow_x, shadow_y))


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
    """Smoothly interpolate entity screen positions and add idle bob."""
    world_position = entity_world_position(renderer, entity)
    if world_position is None:
        return None

    target_px, target_py = screen_rect_for_tile(renderer, world_position[0], world_position[1], min_x, max_y)
    previous = renderer._entity_last_positions.get(entity.name)
    if previous is None:
        px = float(target_px)
        py = float(target_py)
    else:
        px = previous[0] + (target_px - previous[0]) * 0.35
        py = previous[1] + (target_py - previous[1]) * 0.35

    bob_amplitude = float(getattr(renderable, "bob_amplitude", 0.0))
    bob_speed = float(getattr(renderable, "bob_speed", 1.6))
    if bob_amplitude > 0:
        py -= math.sin(time.monotonic() * bob_speed * math.tau) * bob_amplitude * renderer.tile_size

    renderer._entity_last_positions[entity.name] = (px, py)
    return int(round(px)), int(round(py))


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
    inventory_items = entity_inventory_items(inspected)
    title_font = renderer.hud_font
    body_font = renderer.small_font
    metrics = selected_card_metrics(renderer, stat_count=len(stats), inventory_line_count=min(4, len(inventory_items)))
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
    inventory_header_surface = body_font.render("Inventory:", True, (232, 208, 164)) if inventory_items else None
    inventory_item_surfaces = [body_font.render(f"- {item_name}", True, (189, 196, 206)) for item_name in inventory_items[:4]]

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


def draw_overlay_item(
    renderer: "Pygame_Renderer",
    sprite_name: str,
    px: int,
    py: int,
    *,
    mode: str = "badge",
    scale: float | None = None,
) -> None:
    """Draw an overlay sprite on top of an entity using the requested style."""
    if mode == "full":
        overlay_size = renderer.tile_size
        anchor = "top_left"
    elif mode == "center":
        ratio = scale if scale is not None else 0.72
        overlay_size = max(20, int(renderer.tile_size * ratio))
        anchor = "center"
    else:
        ratio = scale if scale is not None else 0.5
        overlay_size = max(18, int(renderer.tile_size * ratio))
        anchor = "top_right"

    blit_scaled_sprite(
        renderer,
        sprite_name,
        px,
        py,
        width=overlay_size,
        height=overlay_size,
        anchor=anchor,
    )


def draw_container_overlay(
    renderer: "Pygame_Renderer",
    container: Any,
    px: int,
    py: int,
) -> None:
    """Draw up to 4 container items in a 2x2 grid with optional ellipsis."""
    visible_items = container.visible_contents()[:4]
    if not visible_items:
        return

    grid_size = 2
    item_size = max(16, int(renderer.tile_size * 0.45))
    gap = max(2, int(renderer.tile_size * 0.05))
    total_size = grid_size * item_size + (grid_size - 1) * gap
    start_x = px + (renderer.tile_size - total_size) // 2
    start_y = py + (renderer.tile_size - total_size) // 2

    for idx, item in enumerate(visible_items[:4]):
        row = idx // 2
        col = idx % 2
        item_px = start_x + col * (item_size + gap)
        item_py = start_y + row * (item_size + gap)

        item_renderable = item.get_component(Renderable)
        if item_renderable is not None:
            blit_scaled_sprite(
                renderer,
                item_renderable.sprite_path,
                item_px,
                item_py,
                width=item_size,
                height=item_size,
                anchor="top_left",
            )

    # Draw ellipsis if more than 4 items
    total_items = len(container.visible_contents())
    if total_items > 4:
        ellipsis_x = start_x + total_size + gap
        ellipsis_y = start_y + total_size - item_size // 2
        ellipsis_surface = renderer.small_font.render("...", True, (200, 200, 200))
        renderer.effect_surface.blit(ellipsis_surface, (ellipsis_x, ellipsis_y))


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
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.effect_surface
        try:
            draw_overlay_item(
                renderer,
                renderable.overlay_sprite,
                px,
                py,
                mode=getattr(renderable, "overlay_mode", "badge"),
                scale=getattr(renderable, "overlay_scale", None),
            )
        finally:
            renderer.world_surface = previous_world_surface

    # Check if entity has a Container component that should be rendered
    from word_play.presets.systems.containers import Container
    container = entity.get_component(Container)
    if container is not None and container.is_open:
        previous_world_surface = renderer.world_surface
        renderer.world_surface = renderer.effect_surface
        try:
            draw_container_overlay(renderer, container, px, py)
        finally:
            renderer.world_surface = previous_world_surface

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

    blit_scaled_sprite(
        renderer,
        sprite_name,
        px,
        py,
        width=renderer.tile_size,
        height=renderer.tile_size,
        anchor="top_left",
    )


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
    """Render the bottom HUD panel with header text and recent messages."""
    if getattr(env, "hide_bottom_hud", False):
        return

    hud_top = height - renderer.hud_height
    panel_rect = pygame.Rect(x_offset, hud_top, width, renderer.hud_height)
    pygame.draw.rect(renderer.screen, (14, 17, 24), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (x_offset, hud_top), (x_offset + width, hud_top), 2)

    header_text = getattr(env, "hud_header", None)
    if header_text is None:
        score = getattr(env, "score", 0)
        tick = getattr(env, "tick", 0)
        current_phase = getattr(env, "current_phase", "N/A")
        header_text = f"Tick {tick}   Score {score}   Current Phase {current_phase}"

    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (x_offset + renderer.margin, hud_top + 12))

    hud_lines = list(getattr(env, "hud_lines", []))

    health_lines: list[str] = []
    if getattr(env, "state", None) is not None:
        agents = list(getattr(env, "agents", []))
        seen_entities: set[int] = set()
        for entity in agents + list(getattr(env.state, "entities", [])):
            if id(entity) in seen_entities:
                continue
            seen_entities.add(id(entity))
            health_value = entity_health_value(entity)
            if health_value is None:
                continue
            max_health = None
            for component in entity.components.values():
                if hasattr(component, "max_health"):
                    max_health = getattr(component, "max_health")
                    break
            if max_health is None:
                health_lines.append(f"{entity.name}: {int(health_value)} HP")
            else:
                health_lines.append(f"{entity.name}: {int(health_value)}/{int(max_health)} HP")
    if health_lines:
        hud_lines = [*health_lines[:4], *hud_lines]
    if not hud_lines:
        event_log = getattr(env, "event_log", [])
        recent_events = event_log[-3:] if event_log else ["Kitchen ready."]
        hud_lines = [f"- {message}" for message in recent_events]

    text_right = x_offset + width - renderer.margin
    for index, message in enumerate(hud_lines[:6]):
        color = (189, 196, 206) if index < 3 else (235, 213, 154)
        wrapped = wrap_text_lines(renderer.small_font, str(message), max_width=max(220, text_right - (x_offset + renderer.margin)))
        row_y = hud_top + 44 + index * (renderer.small_font.get_linesize() + 4)
        if wrapped:
            surface = renderer.small_font.render(wrapped[0], True, color)
            renderer.screen.blit(surface, (x_offset + renderer.margin, row_y))


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
    if not final_boss_defeated and not any(terminations) and not any(truncations):
        return

    if final_boss_defeated:
        title = "Raid Complete"
        subtitle = "The Ash Warden has fallen."
        accent = (206, 182, 92)
    elif any(truncations):
        title = "Experiment Completed"
        subtitle = str(getattr(env, "completion_subtitle", "The run has finished."))
        accent = (149, 161, 178)
    else:
        title = "Defeat"
        subtitle = "The raider fell in battle."
        accent = (170, 82, 82)

    overlay = pygame.Surface((world_width, world_height), pygame.SRCALPHA)
    overlay.fill((8, 10, 16, 170))
    renderer.screen.blit(overlay, (world_x, 0))

    box_width = min(max(320, renderer.tile_size * 6), world_width - 40)
    box_height = max(120, renderer.tile_size * 2 + 36)
    box_x = (world_width - box_width) // 2
    box_y = (world_height - box_height) // 2
    panel_rect = pygame.Rect(world_x + box_x, box_y, box_width, box_height)
    pygame.draw.rect(renderer.screen, (18, 22, 30), panel_rect, border_radius=18)
    pygame.draw.rect(renderer.screen, accent, panel_rect, width=3, border_radius=18)

    title_surface = renderer.font.render(title, True, (245, 247, 250))
    subtitle_surface = renderer.hud_font.render(subtitle, True, accent)
    title_x = box_x + (box_width - title_surface.get_width()) // 2
    subtitle_x = box_x + (box_width - subtitle_surface.get_width()) // 2
    renderer.screen.blit(title_surface, (title_x, box_y + 24))
    renderer.screen.blit(subtitle_surface, (subtitle_x, box_y + 24 + title_surface.get_height() + 12))


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


def draw_speech_bubbles(
    renderer: "Pygame_Renderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    """Draw speech bubbles above entities using rounded rects and tail polygons."""
    speech_bubbles = list(getattr(env, "speech_bubbles", []))
    if not speech_bubbles:
        return

    for bubble in speech_bubbles:
        entity_name = bubble.get("entity_name")
        text = str(bubble.get("text", "")).strip()
        if not entity_name or not text or entity_name not in entity_positions:
            continue

        px, py = entity_positions[entity_name]
        anchor_x = px + renderer.tile_size // 2
        anchor_y = py + max(4, renderer.tile_size // 6)
        bubble_width = max(int(renderer.tile_size * 2.55), 140)
        bubble_height = max(int(renderer.tile_size * 1.18), 54)
        pad_left = max(10, int(renderer.tile_size * 0.18))
        pad_right = max(10, int(renderer.tile_size * 0.18))
        pad_top = max(8, int(renderer.tile_size * 0.14))
        pad_bottom = max(9, int(renderer.tile_size * 0.16))
        tail_width = max(14, renderer.tile_size // 2)
        tail_height = max(10, int(renderer.tile_size * 0.26))
        radius = max(10, int(renderer.tile_size * 0.24))
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
    needs_sidebar = bool(sidebar_lines)
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
