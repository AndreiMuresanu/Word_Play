from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

from word_play.core import Entity

from .assets import get_or_load_image, get_scaled_image, resolve_wall_sprite
from .wall_geometry import (
    collect_wall_positions,
    normalize_background_item,
    screen_position_for_entity,
    screen_rect_for_tile,
    wall_neighbor_mask,
    wall_variant,
    world_bounds,
)
from .renderer import Renderable
from .runtime import ensure_screen_size

if TYPE_CHECKING:
    from word_play.core import Environment

    from .renderer import PygameRenderer


def visible_renderables(env: "Environment") -> list[tuple[int, Entity, Renderable]]:
    renderables: list[tuple[int, Entity, Renderable]] = []
    for entity in env.state.entities:
        renderable = entity.get_component(Renderable)
        if renderable is not None and renderable.visible:
            renderables.append((renderable.z_index, entity, renderable))
    renderables.sort(key=lambda item: item[0])
    return renderables


def background_items(env: "Environment", renderer: "PygameRenderer") -> list[dict[str, Any]]:
    return [normalize_background_item(item) for item in renderer.layout.background(env)]


def entity_health_value(entity: Entity) -> float | None:
    for component in entity.components.values():
        if hasattr(component, "current_health"):
            return float(getattr(component, "current_health"))
        if hasattr(component, "health"):
            return float(getattr(component, "health"))
    return None


def update_damage_flash_state(renderer: "PygameRenderer", env: "Environment") -> None:
    now = time.monotonic()
    active_names = {entity.name for entity in env.state.entities}
    renderer._damage_flash_until = {
        name: until
        for name, until in renderer._damage_flash_until.items()
        if name in active_names and until > now
    }

    next_health_values: dict[str, float] = {}
    for entity in env.state.entities:
        health_value = entity_health_value(entity)
        if health_value is None:
            continue
        next_health_values[entity.name] = health_value
        previous_value = renderer._last_health_values.get(entity.name)
        if previous_value is not None and health_value < previous_value:
            renderer._damage_flash_until[entity.name] = now + 1.0

    renderer._last_health_values = next_health_values


def flash_tinted_surface(image: Any, *, tint: tuple[int, int, int], alpha: int) -> Any:
    tinted = image.copy()
    overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
    overlay.fill((*tint, alpha))
    tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted


def blit_scaled_sprite(
    renderer: "PygameRenderer",
    sprite_name: str,
    px: int,
    py: int,
    *,
    width: int,
    height: int,
    anchor: str = "center",
    missing_ok: bool = False,
) -> bool:
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

    renderer.screen.blit(image, (draw_x, draw_y))
    return True


def draw_floor_tile(renderer: "PygameRenderer", px: int, py: int, color: tuple[int, int, int]) -> None:
    rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
    pygame.draw.rect(renderer.screen, color, rect)


def draw_wall_tile(renderer: "PygameRenderer", px: int, py: int, color: tuple[int, int, int], neighbors: dict[str, bool]) -> None:
    variant = wall_variant(neighbors)
    base = color
    highlight = tuple(min(255, c + 32) for c in color)
    shadow = tuple(max(0, c - 28) for c in color)
    rect = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
    radius = max(6, renderer.tile_size // 5)

    pygame.draw.rect(renderer.screen, base, rect, border_radius=radius)
    pygame.draw.rect(renderer.screen, shadow, rect, width=max(1, renderer.tile_size // 10), border_radius=radius)

    edge = max(4, renderer.tile_size // 6)
    if not neighbors["n"]:
        pygame.draw.rect(renderer.screen, highlight, (px, py, renderer.tile_size, edge), border_top_left_radius=radius, border_top_right_radius=radius)
    if not neighbors["s"]:
        pygame.draw.rect(
            renderer.screen,
            shadow,
            (px, py + renderer.tile_size - edge, renderer.tile_size, edge),
            border_bottom_left_radius=radius,
            border_bottom_right_radius=radius,
        )
    if not neighbors["w"]:
        pygame.draw.rect(renderer.screen, highlight, (px, py, edge, renderer.tile_size), border_top_left_radius=radius, border_bottom_left_radius=radius)
    if not neighbors["e"]:
        pygame.draw.rect(
            renderer.screen,
            shadow,
            (px + renderer.tile_size - edge, py, edge, renderer.tile_size),
            border_top_right_radius=radius,
            border_bottom_right_radius=radius,
        )

    cut_radius = max(4, renderer.tile_size // 4)
    if neighbors["n"] and neighbors["e"] and not neighbors["ne"]:
        pygame.draw.circle(renderer.screen, (24, 24, 28), (px + renderer.tile_size - cut_radius, py + cut_radius), cut_radius)
    if neighbors["e"] and neighbors["s"] and not neighbors["se"]:
        pygame.draw.circle(renderer.screen, (20, 20, 24), (px + renderer.tile_size - cut_radius, py + renderer.tile_size - cut_radius), cut_radius)
    if neighbors["s"] and neighbors["w"] and not neighbors["sw"]:
        pygame.draw.circle(renderer.screen, (20, 20, 24), (px + cut_radius, py + renderer.tile_size - cut_radius), cut_radius)
    if neighbors["w"] and neighbors["n"] and not neighbors["nw"]:
        pygame.draw.circle(renderer.screen, (24, 24, 28), (px + cut_radius, py + cut_radius), cut_radius)

    accent_color = {
        "pillar": (255, 232, 184),
        "end_cap": (250, 214, 150),
        "corner": (246, 196, 118),
        "straight": (235, 180, 103),
        "t_junction": (227, 166, 91),
        "cross": (214, 152, 78),
    }[variant]
    dot_radius = max(2, renderer.tile_size // 12)
    pygame.draw.circle(renderer.screen, accent_color, rect.center, dot_radius)


def draw_wall_sprite(renderer: "PygameRenderer", wall_set: str, px: int, py: int, neighbors: dict[str, bool]) -> bool:
    sprite_name = resolve_wall_sprite(renderer, wall_set, neighbors)
    if sprite_name is None:
        return False
    return blit_scaled_sprite(
        renderer,
        sprite_name,
        px,
        py,
        width=renderer.tile_size,
        height=renderer.tile_size,
        anchor="top_left",
        missing_ok=True,
    )


def draw_wall_background_tile(
    renderer: "PygameRenderer",
    item: dict[str, Any],
    px: int,
    py: int,
    *,
    wall_positions: set[tuple[int, int]],
) -> bool:
    if item.get("kind") != "wall":
        return False

    wall_set = item.get("wall_set")
    if not wall_set:
        return False

    backdrop = pygame.Rect(px, py, renderer.tile_size, renderer.tile_size)
    pygame.draw.rect(renderer.screen, (24, 20, 18), backdrop)
    neighbors = wall_neighbor_mask(int(item["x"]), int(item["y"]), wall_positions)
    return draw_wall_sprite(renderer, str(wall_set), px, py, neighbors)


def draw_overlay_item(
    renderer: "PygameRenderer",
    sprite_name: str,
    px: int,
    py: int,
    *,
    mode: str = "badge",
    scale: float | None = None,
) -> None:
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


def draw_entity(renderer: "PygameRenderer", entity: Entity, renderable: Renderable, px: int, py: int) -> None:
    image = get_or_load_image(renderer, renderable.sprite_path)
    if image is None:
        raise FileNotFoundError(
            f"Sprite renderer expected a valid sprite path for '{entity.name}', but could not resolve '{renderable.sprite_path}'."
        )
    flash_until = renderer._damage_flash_until.get(entity.name, 0.0)
    if flash_until > time.monotonic():
        image = flash_tinted_surface(image, tint=(190, 20, 20), alpha=140)
    scaled_image = pygame.transform.scale(image, (renderer.tile_size, renderer.tile_size))
    renderer.screen.blit(scaled_image, (px, py))

    if renderable.overlay_sprite:
        draw_overlay_item(
            renderer,
            renderable.overlay_sprite,
            px,
            py,
            mode=getattr(renderable, "overlay_mode", "badge"),
            scale=getattr(renderable, "overlay_scale", None),
        )


def draw_hit_effects(
    renderer: "PygameRenderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
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


def draw_background_tile(
    renderer: "PygameRenderer",
    item: dict[str, Any],
    px: int,
    py: int,
    *,
    wall_positions: set[tuple[int, int]],
) -> None:
    kind = item.get("kind", "floor")
    if draw_wall_background_tile(renderer, item, px, py, wall_positions=wall_positions):
        return

    sprite_name = item.get("sprite")
    if sprite_name:
        if blit_scaled_sprite(
            renderer,
            sprite_name,
            px,
            py,
            width=renderer.tile_size,
            height=renderer.tile_size,
            anchor="top_left",
            missing_ok=True,
        ):
            return

    color = item.get("color")
    if kind == "floor":
        draw_floor_tile(renderer, px, py, color or (60, 70, 82))
        return
    if kind == "wall":
        neighbors = wall_neighbor_mask(int(item["x"]), int(item["y"]), wall_positions)
        draw_wall_tile(renderer, px, py, color or (122, 96, 72), neighbors)
        return
    draw_floor_tile(renderer, px, py, color or (72, 80, 92))


def draw_grid_overlay(renderer: "PygameRenderer", min_x: int, max_x: int, min_y: int, max_y: int) -> None:
    overlay_color = (30, 30, 34)
    for x in range(min_x, max_x + 2):
        px = renderer.margin + (x - min_x) * renderer.tile_size
        pygame.draw.line(
            renderer.screen,
            overlay_color,
            (px, renderer.margin),
            (px, renderer.margin + (max_y - min_y + 1) * renderer.tile_size),
            2,
        )
    for y in range(min_y, max_y + 2):
        py = renderer.margin + (max_y - y + 1) * renderer.tile_size
        pygame.draw.line(
            renderer.screen,
            overlay_color,
            (renderer.margin, py),
            (renderer.margin + (max_x - min_x + 1) * renderer.tile_size, py),
            2,
        )


def draw_hud_panel(renderer: "PygameRenderer", env: "Environment", width: int, height: int) -> None:
    hud_top = height - renderer.hud_height
    panel_rect = pygame.Rect(0, hud_top, width, renderer.hud_height)
    pygame.draw.rect(renderer.screen, (14, 17, 24), panel_rect)
    pygame.draw.line(renderer.screen, (52, 63, 79), (0, hud_top), (width, hud_top), 2)

    header_text = getattr(env, "hud_header", None)
    if header_text is None:
        score = getattr(env, "score", 0)
        tick = getattr(env, "tick", 0)
        deliveries = getattr(env, "deliveries", 0)
        header_text = f"Tick {tick}   Score {score}   Deliveries {deliveries}"

    header = renderer.hud_font.render(str(header_text), True, (240, 242, 245))
    renderer.screen.blit(header, (renderer.margin, hud_top + 12))

    hud_lines = list(getattr(env, "hud_lines", []))
    if not hud_lines:
        event_log = getattr(env, "event_log", [])
        recent_events = event_log[-3:] if event_log else ["Kitchen ready."]
        hud_lines = [f"- {message}" for message in recent_events]

    for index, message in enumerate(hud_lines[:6]):
        color = (189, 196, 206) if index < 3 else (235, 213, 154)
        surface = renderer.small_font.render(str(message), True, color)
        renderer.screen.blit(surface, (renderer.margin, hud_top + 44 + index * (renderer.small_font.get_linesize() + 4)))


def wrap_text_lines(font: Any, text: str, max_width: int) -> list[str]:
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
    renderer: "PygameRenderer",
    env: "Environment",
    entity_positions: dict[str, tuple[int, int]],
) -> None:
    speech_bubbles = list(getattr(env, "speech_bubbles", []))
    if not speech_bubbles:
        return

    bubble_sprite_name = getattr(env, "speech_bubble_sprite", None) or "src/chat_interface/speech_bubble.png"
    bubble_sprite = get_or_load_image(renderer, bubble_sprite_name)

    for bubble in speech_bubbles:
        entity_name = bubble.get("entity_name")
        text = str(bubble.get("text", "")).strip()
        if not entity_name or not text or entity_name not in entity_positions:
            continue

        px, py = entity_positions[entity_name]
        bubble_width = max(int(renderer.tile_size * 2.75), 148)
        bubble_height = max(int(renderer.tile_size * 1.7), 72)
        pad_left = max(14, renderer.tile_size // 3)
        pad_right = max(14, renderer.tile_size // 3)
        pad_top = max(10, renderer.tile_size // 4)
        pad_bottom = max(22, renderer.tile_size // 2)
        text_max_width = bubble_width - pad_left - pad_right
        speech_font, lines = fit_wrapped_text_lines(
            renderer.speech_fonts,
            text,
            max_width=text_max_width,
            max_lines=3,
        )
        text_surfaces = [speech_font.render(line, True, (18, 16, 14)) for line in lines]
        text_width = max(surface.get_width() for surface in text_surfaces)
        line_gap = 1
        text_height = sum(surface.get_height() for surface in text_surfaces) + max(0, len(text_surfaces) - 1) * line_gap
        bubble_width = max(bubble_width, text_width + pad_left + pad_right)
        bubble_height = max(bubble_height, text_height + pad_top + pad_bottom)
        bubble_x = px + (renderer.tile_size - bubble_width) // 2
        bubble_y = max(6, py - bubble_height + 10)
        content_left = bubble_x + pad_left
        content_top = bubble_y + pad_top
        content_width = bubble_width - pad_left - pad_right
        content_height = bubble_height - pad_top - pad_bottom

        if bubble_sprite is not None:
            scaled_bubble = pygame.transform.scale(bubble_sprite, (bubble_width, bubble_height))
            renderer.screen.blit(scaled_bubble, (bubble_x, bubble_y))
        else:
            bubble_rect = pygame.Rect(bubble_x, bubble_y, bubble_width, bubble_height)
            pygame.draw.rect(renderer.screen, (250, 245, 233), bubble_rect, border_radius=14)
            pygame.draw.rect(renderer.screen, (56, 46, 39), bubble_rect, width=2, border_radius=14)

        text_y = content_top + max(0, (content_height - text_height) // 2)
        for surface in text_surfaces:
            text_x = content_left + max(0, (content_width - surface.get_width()) // 2)
            renderer.screen.blit(surface, (text_x, text_y))
            text_y += surface.get_height() + line_gap


def render_environment(renderer: "PygameRenderer", env: "Environment") -> None:
    update_damage_flash_state(renderer, env)
    background = background_items(env, renderer)
    renderables = visible_renderables(env)
    min_x, max_x, min_y, max_y = world_bounds(renderer, background, renderables)

    grid_width = max(1, max_x - min_x + 1)
    grid_height = max(1, max_y - min_y + 1)
    width = renderer.margin * 2 + grid_width * renderer.tile_size
    height = renderer.margin * 2 + grid_height * renderer.tile_size + renderer.hud_height
    ensure_screen_size(renderer, width, height)

    renderer.screen.fill((8, 11, 16))
    wall_positions = collect_wall_positions(background)

    for item in background:
        x = int(item["x"])
        y = int(item["y"])
        px, py = screen_rect_for_tile(renderer, x, y, min_x, max_y)
        draw_background_tile(renderer, item, px, py, wall_positions=wall_positions)

    positions: dict[str, tuple[int, int]] = {}
    for _, entity, renderable in renderables:
        position = screen_position_for_entity(renderer, entity, min_x=min_x, max_y=max_y)
        if position is None:
            continue
        px, py = position
        positions[entity.name] = position
        draw_entity(renderer, entity, renderable, px, py)

    draw_hit_effects(renderer, env, positions)
    draw_speech_bubbles(renderer, env, positions)

    if getattr(env, "draw_grid_overlay", renderer.default_draw_grid_overlay):
        draw_grid_overlay(renderer, min_x, max_x, min_y, max_y)

    draw_hud_panel(renderer, env, width, height)
    pygame.display.flip()
