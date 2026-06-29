"""Trade window rendering — public offers, trade sessions, chat sessions, negotiation.

Ported from bryan/trading_rendering, refactored to use .assets imports.
"""
from __future__ import annotations

import math, textwrap, pygame
from typing import Any, TYPE_CHECKING

from word_play.presets.renderers.pygame_renderer.renderable import Renderable

if TYPE_CHECKING:
    from word_play.core import Entity
    from word_play.presets.renderers.pygame_renderer.renderer import Pygame_Renderer


RUSTIC_TRADE_WINDOW_SPRITE = "sprite_library/src/ui/trade_window_rustic.png"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _chat_message_text(message: Any) -> str:
    if isinstance(message, dict):
        if "sender" in message and "text" in message:
            return f"{message['sender']}: {message['text']}"
        payload = message.get("payload", {})
        return str(payload.get("text", "") or payload.get("content", "") or message)
    return str(message)


def parse_trade_message(text: str) -> dict[str, Any] | None:
    try:
        return {"left_name": "Trader 1", "right_name": "Trader 2", "accepted": "yes" if "accepted" in text.lower() else ""}
    except Exception:
        return None


def _trade_items_from_field(text: str) -> list[str]:
    if not text or text.lower() == "none":
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _trade_session_rect(
    renderer: "Pygame_Renderer",
    left_pos: tuple[int, int],
    right_pos: tuple[int, int],
    panel_width: int,
    panel_height: int,
) -> pygame.Rect:
    surface = renderer.effect_surface
    sw, sh = surface.get_width(), surface.get_height()
    center_x = (left_pos[0] + right_pos[0]) // 2 + renderer.tile_size // 2
    y = max(20, min(left_pos[1], right_pos[1]) - panel_height - 20)
    if y < 20:
        y = max(left_pos[1] + renderer.tile_size, right_pos[1] + renderer.tile_size) + 20
    x = max(8, min(center_x - panel_width // 2, sw - panel_width - 8))
    return pygame.Rect(x, min(y, sh - panel_height - 8), panel_width, panel_height)


def _chat_session_rect(
    renderer: "Pygame_Renderer",
    participant_positions: list[tuple[int, int]],
    panel_width: int,
    panel_height: int,
) -> pygame.Rect:
    surface = renderer.effect_surface
    sw, sh = surface.get_width(), surface.get_height()
    avg_x = sum(p[0] for p in participant_positions) // max(1, len(participant_positions)) + renderer.tile_size // 2
    max_y = max(p[1] for p in participant_positions)
    y = sh - panel_height - 12
    x = max(8, min(avg_x - panel_width // 2, sw - panel_width - 8))
    return pygame.Rect(x, y, panel_width, panel_height)


# ═══════════════════════════════════════════════════════════════════════
# Drawing primitives
# ═══════════════════════════════════════════════════════════════════════

def _draw_trade_currency(renderer: "Pygame_Renderer", x: int, y: int, amount: str, font: Any) -> None:
    surface = renderer.effect_surface
    radius = max(6, int(renderer.tile_size * 0.12))
    label = font.render(f"{amount}g", True, (66, 42, 16))

    content_w = radius * 2 + 4 + label.get_width()
    plate = pygame.Rect(x - 5, y - 4, content_w + 10, radius * 2 + 8)
    pygame.draw.rect(surface, (231, 203, 146), plate, border_radius=plate.height // 2)
    pygame.draw.rect(surface, (120, 84, 40), plate, width=1, border_radius=plate.height // 2)

    center = (x + radius, y + radius)
    pygame.draw.circle(surface, (150, 104, 28), center, radius)
    pygame.draw.circle(surface, (245, 205, 84), center, max(2, radius - 2))
    # Tiny specular highlight on the coin.
    pygame.draw.circle(surface, (255, 238, 158), (center[0] - radius // 3, center[1] - radius // 3), max(1, radius // 4))
    surface.blit(label, (x + radius * 2 + 4, y + radius - label.get_height() // 2))


def _trade_currency_width(renderer: "Pygame_Renderer", amount: str, font: Any) -> int:
    radius = max(6, int(renderer.tile_size * 0.12))
    return radius * 2 + 4 + font.size(f"{amount}g")[0]


def _draw_exchange_emblem(surface: pygame.Surface, cx: int, cy: int, size: int) -> None:
    """Two opposed arrows (⇄) marking the swap between the two offers."""
    s = max(7, size)
    gap = max(2, s // 4)
    shaft = (236, 206, 150)
    edge = (120, 80, 38)
    # Disc backing so the emblem reads over the wood and divider.
    pygame.draw.circle(surface, (60, 40, 24), (cx, cy), s)
    pygame.draw.circle(surface, edge, (cx, cy), s, width=1)
    for sign in (-1, 1):
        ay = cy - sign * gap
        x0, x1 = cx - s + 3, cx + s - 3
        if sign > 0:
            x0, x1 = x1, x0  # bottom arrow points left
        pygame.draw.line(surface, shaft, (x0, ay), (x1, ay), width=max(2, s // 5))
        head = max(3, s // 2)
        tip = (x1, ay)
        back = x1 - sign * 0  # direction handled by ordering below
        dir_x = 1 if x1 > x0 else -1
        pygame.draw.polygon(surface, shaft, [
            tip,
            (x1 - dir_x * head, ay - head // 2),
            (x1 - dir_x * head, ay + head // 2),
        ])


def _fit_trade_item_sprite(sprite: pygame.Surface, max_size: int) -> pygame.Surface:
    visible_rect = sprite.get_bounding_rect()
    if visible_rect.width <= 0 or visible_rect.height <= 0:
        visible_rect = sprite.get_rect()
    cropped = sprite.subsurface(visible_rect)
    scale_factor = max_size / max(visible_rect.width, visible_rect.height)
    return pygame.transform.scale(cropped, (
        max(1, int(round(visible_rect.width * scale_factor))),
        max(1, int(round(visible_rect.height * scale_factor))),
    ))


def _draw_trade_offer_grid(
    renderer: "Pygame_Renderer",
    rect: pygame.Rect,
    items: list[str],
    entity_lookup: dict[str, "Entity"],
    font: Any,
    gold: tuple[int, int, int] = (245, 214, 115),
) -> None:
    from .assets import get_or_load_image

    surface = renderer.effect_surface
    cell_size = rect.width // 2
    slot_pad = max(2, cell_size // 11)

    # Dark backing board behind the four slots.
    backing = rect.inflate(slot_pad, slot_pad)
    pygame.draw.rect(surface, (34, 22, 14), backing, border_radius=4)
    pygame.draw.rect(surface, (74, 49, 28), backing, width=1, border_radius=4)

    visible_items = items[:4] if len(items) <= 4 else items[:3] + ["..."]
    for idx in range(4):
        cell = pygame.Rect(
            rect.left + (idx % 2) * cell_size + slot_pad,
            rect.top + (idx // 2) * cell_size + slot_pad,
            cell_size - 2 * slot_pad,
            cell_size - 2 * slot_pad,
        )
        # Recessed slot: dark fill, dark top/left edge, lit bottom/right edge.
        pygame.draw.rect(surface, (58, 39, 24), cell, border_radius=3)
        pygame.draw.line(surface, (28, 18, 12), cell.topleft, (cell.right, cell.top))
        pygame.draw.line(surface, (28, 18, 12), cell.topleft, (cell.left, cell.bottom))
        pygame.draw.line(surface, (104, 71, 42), (cell.left, cell.bottom), cell.bottomright)
        pygame.draw.line(surface, (104, 71, 42), (cell.right, cell.top), cell.bottomright)
        pygame.draw.rect(surface, (22, 14, 9), cell, width=1, border_radius=3)

        item_name = visible_items[idx] if idx < len(visible_items) else None
        if not item_name:
            continue
        if item_name == "...":
            label = font.render("…", True, gold)
            surface.blit(label, (cell.centerx - label.get_width() // 2, cell.centery - label.get_height() // 2))
            continue
        item_entity = entity_lookup.get(item_name)
        renderable = item_entity.get_component(Renderable) if item_entity is not None else None
        base_sprite = get_or_load_image(renderer, renderable.sprite_path) if renderable and renderable.sprite_path else None
        if base_sprite is not None:
            sprite = _fit_trade_item_sprite(base_sprite, max(12, int(cell.width * 0.80)))
            surface.blit(sprite, (cell.centerx - sprite.get_width() // 2, cell.centery - sprite.get_height() // 2))
        else:
            label = font.render(item_name[:2].upper(), True, (240, 222, 166))
            surface.blit(label, (cell.centerx - label.get_width() // 2, cell.centery - label.get_height() // 2))


def _draw_trade_label(surface: pygame.Surface, font: Any, label: str, center_x: int, y: int) -> None:
    text = font.render(label, True, (255, 235, 156))
    surface.blit(text, (center_x - text.get_width() // 2, y))


def _draw_trade_name_section(
    renderer: "Pygame_Renderer",
    rect: pygame.Rect,
    font: Any,
    name: str,
) -> None:
    surface = renderer.effect_surface
    pygame.draw.rect(surface, (55, 34, 20), rect)
    pygame.draw.rect(surface, (151, 94, 43), rect, width=1)
    _draw_trade_label(surface, font, name, rect.centerx, rect.top + 2)


def _draw_trade_log_line(
    surface: pygame.Surface,
    font: Any,
    text: str,
    x: int,
    y: int,
    max_width: int,
) -> None:
    line = _ellipsize_text(font, text.strip(), max_width)
    if not line:
        return
    rendered = font.render(line, True, (230, 222, 194))
    surface.blit(rendered, (x, y))


def _ellipsize_text(font: Any, text: str, max_width: int) -> str:
    if not text or max_width <= 0:
        return ""
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = "..."
    if font.size(ellipsis)[0] > max_width:
        return ""

    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip() + ellipsis
        if font.size(candidate)[0] <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ellipsis


def _draw_trade_window_bg(renderer: "Pygame_Renderer", rect: pygame.Rect) -> None:
    from .assets import get_scaled_image

    bg = get_scaled_image(renderer, RUSTIC_TRADE_WINDOW_SPRITE, rect.width, rect.height)
    if bg is not None:
        renderer.effect_surface.blit(bg, rect)
    else:
        pygame.draw.rect(renderer.effect_surface, (118, 72, 35), rect)
        pygame.draw.rect(renderer.effect_surface, (222, 184, 118), rect.inflate(-18, -16))


# ═══════════════════════════════════════════════════════════════════════
# Trade session window (private trade, shared panel between two agents)
# ═══════════════════════════════════════════════════════════════════════

def draw_trade_session_window(
    renderer: "Pygame_Renderer",
    left_position: tuple[int, int],
    right_position: tuple[int, int],
    trade_data: dict[str, Any],
    entity_lookup: dict[str, "Entity"],
    scale: float,
) -> None:
    tile_s = renderer.tile_size
    left_name = trade_data.get("left", "Trader")
    right_name = trade_data.get("right", "Trader")
    left_items = _trade_items_from_field(trade_data.get("left_offer", "none"))
    right_items = _trade_items_from_field(trade_data.get("right_offer", "none"))
    left_currency = trade_data.get("left_currency", "").strip()
    right_currency = trade_data.get("right_currency", "").strip()
    messages = [_chat_message_text(m) for m in trade_data.get("messages", [])][-2:]

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

    log_height = 0
    if messages:
        log_line_gap = max(1, int(tile_s * 0.02))
        log_height = max(int(tile_s * 0.42), len(messages) * log_font.get_height() + max(0, len(messages) - 1) * log_line_gap + 8)

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
    cell_size = max(18, min(int(tile_s * 0.48), grid_area_width // 2))
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
    pygame.draw.line(renderer.effect_surface, (139, 90, 44), (panel_rect.centerx, divider_top), (panel_rect.centerx, divider_bottom), width=2)

    left_grid = pygame.Rect(left_area_left + max(0, (left_area_right - left_area_left - grid_size) // 2), grid_y, grid_size, grid_size)
    right_grid = pygame.Rect(right_area_left + max(0, (right_area_right - right_area_left - grid_size) // 2), grid_y, grid_size, grid_size)
    _draw_trade_name_section(renderer, pygame.Rect(left_grid.left, label_y, left_grid.width, name_h), title_font, left_name)
    _draw_trade_name_section(renderer, pygame.Rect(right_grid.left, label_y, right_grid.width, name_h), title_font, right_name)
    _draw_trade_offer_grid(renderer, left_grid, left_items, entity_lookup, item_font, gold)
    _draw_trade_offer_grid(renderer, right_grid, right_items, entity_lookup, item_font, gold)

    _draw_exchange_emblem(renderer.effect_surface, panel_rect.centerx, left_grid.centery, max(9, int(tile_s * 0.16)))

    if left_currency:
        cw = _trade_currency_width(renderer, left_currency, item_font)
        _draw_trade_currency(renderer, left_grid.centerx - cw // 2, currency_y, left_currency, item_font)
    if right_currency:
        cw = _trade_currency_width(renderer, right_currency, item_font)
        _draw_trade_currency(renderer, right_grid.centerx - cw // 2, currency_y, right_currency, item_font)

    if trade_data.get("accepted") == "yes":
        surface = renderer.effect_surface
        done = status_font.render("DEAL", True, (244, 250, 232))
        badge = pygame.Rect(0, 0, done.get_width() + int(tile_s * 0.34), done.get_height() + int(tile_s * 0.14))
        badge.center = (panel_rect.centerx, left_grid.centery)
        pygame.draw.rect(surface, (58, 92, 44), badge, border_radius=badge.height // 2)
        pygame.draw.rect(surface, (94, 140, 66), badge, width=2, border_radius=badge.height // 2)
        surface.blit(done, (badge.centerx - done.get_width() // 2, badge.centery - done.get_height() // 2))

    if messages:
        log_rect = pygame.Rect(panel_rect.left + pad_x, panel_rect.bottom - log_height - max(4, int(tile_s * 0.04)), panel_rect.width - pad_x * 2, log_height)
        pygame.draw.rect(renderer.effect_surface, (47, 31, 21), log_rect)
        pygame.draw.rect(renderer.effect_surface, (151, 94, 43), log_rect, width=1)
        line_y = log_rect.top + max(4, int(tile_s * 0.04))
        for line in messages:
            _draw_trade_log_line(renderer.effect_surface, log_font, line, log_rect.left + 4, line_y, log_rect.width - 8)
            line_y += log_font.get_height() + max(1, int(tile_s * 0.02))


# ═══════════════════════════════════════════════════════════════════════
# Chat session window (private conversation, at bottom of screen)
# ═══════════════════════════════════════════════════════════════════════

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
    visible_messages = [_chat_message_text(m) for m in messages[-4:]]
    wrapped_messages: list[list[str]] = []
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
    surface.blit(title_surface, (panel_rect.centerx - title_surface.get_width() // 2, panel_rect.top + max(3, pad_y // 2)))

    text_y = title_rect.bottom + line_gap
    for lines in wrapped_messages:
        for line in lines:
            text_surface = body_font.render(line, True, (30, 25, 22))
            surface.blit(text_surface, (panel_rect.left + pad_x, text_y))
            text_y += body_font.get_height()
        text_y += line_gap


def wrap_text_lines(font: Any, text: str, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        test = f"{current} {word}"
        if font.size(test)[0] <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
