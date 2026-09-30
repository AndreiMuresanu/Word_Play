"""A generic metrics overlay: a parchment panel of stats and sparklines.

Any environment can publish a ``ui.metrics`` dict in its render frame and the
renderer draws it over the world view — no per-environment drawing code.

Frame data shape (all optional except the panel itself)::

    env.render_state.frame["ui.metrics"] = {
        "title": "Round 4 / 8",
        "subtitle": "Commons harvest",
        "rows": [
            {"label": "Fish in lake", "value": "62", "accent": True},
            {"label": "Survived", "value": "8 months"},
            {"label": "Inequality (Gini)", "value": "0.11"},
        ],
        "series": [
            {"label": "Lake stock", "values": [100, 62, 38, 50, 62, 80],
             "threshold": 50, "max": 100},
        ],
        "anchor": "top_left",   # top_left | top_right | bottom_left | bottom_right
        "scale": 1.0,           # shrink/grow the whole card (0.6 = compact corner card)
    }
"""

from __future__ import annotations

from typing import Any

import pygame

from .chrome import Chrome, active_chrome
from .fonts import get_font, render_text


def draw_metrics_overlay(renderer: "Any", scene: "Any") -> None:
    """Draw the ``ui.metrics`` panel published by the environment, if any."""
    metrics = scene.metadata.get("ui.metrics")
    if not metrics:
        return

    scale = max(0.3, min(2.0, float(metrics.get("scale", 1.0))))
    tile = max(10, int(max(24, renderer.tile_size) * scale))
    fonts = _metrics_fonts(tile)
    rows = [r for r in metrics.get("rows", []) if isinstance(r, dict)]
    series = [s for s in metrics.get("series", []) if isinstance(s, dict)]

    pad = max(5, tile // 4)
    row_h = fonts["body"].get_height() + max(2, tile // 14)
    spark_h = max(16, int(tile * 1.0))
    spark_gap = max(6, tile // 8)

    # width follows the widest line of content
    title_w = fonts["title"].size(str(metrics.get("title", "Metrics")))[0]
    if metrics.get("subtitle"):
        title_w = max(title_w, fonts["small"].size(str(metrics["subtitle"]))[0])
    content_w = title_w
    for row in rows:
        w = fonts["body"].size(str(row.get("label", "")))[0] + fonts["body"].size(str(row.get("value", "")))[0] + tile
        content_w = max(content_w, w)
    for s in series:
        content_w = max(content_w, fonts["small"].size(str(s.get("label", "")))[0])
    # cap the card width, but never below what the (unwrappable) title needs
    panel_cap = max(int(tile * 7.5), title_w + pad * 2)
    panel_w = min(panel_cap, max(int(tile * 4.4), content_w + pad * 2))
    spark_w = panel_w - pad * 2

    title_h = fonts["title"].get_height() + (fonts["small"].get_height() if metrics.get("subtitle") else 0)
    panel_h = pad * 2 + title_h + max(3, tile // 12) + len(rows) * row_h
    if series:
        panel_h += spark_gap + len(series) * (spark_h + fonts["small"].get_height() + spark_gap)

    rect = _anchor_rect(renderer, metrics.get("anchor", "top_left"), panel_w, int(panel_h))
    surface = renderer.screen
    chrome = active_chrome(renderer)

    # drop shadow then the chrome's floating card
    shadow = pygame.Surface((rect.width + 8, rect.height + 8), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 70), shadow.get_rect(), border_radius=12)
    surface.blit(shadow, (rect.x - 2, rect.y + 2))
    chrome.draw_card(surface, rect, radius=10)

    x = rect.x + pad
    y = rect.y + pad
    title = render_text(fonts["title"], str(metrics.get("title", "Metrics")), chrome.text_on_card)
    surface.blit(title, (x, y))
    y += title.get_height()
    if metrics.get("subtitle"):
        sub = render_text(fonts["small"], str(metrics["subtitle"]), chrome.text_on_card_soft)
        surface.blit(sub, (x, y))
        y += sub.get_height()
    y += max(3, tile // 12)
    pygame.draw.line(surface, chrome.inset_edge, (x, y), (rect.right - pad, y))
    y += max(3, tile // 14)

    for row in rows:
        accent = bool(row.get("accent"))
        label = render_text(fonts["body"], str(row.get("label", "")), chrome.text_on_card_soft)
        value_color = chrome.accent_deep if accent else chrome.text_on_card
        value = render_text(fonts["body"], str(row.get("value", "")), value_color)
        surface.blit(label, (x, y))
        surface.blit(value, (rect.right - pad - value.get_width(), y))
        y += row_h

    for s in series:
        y += spark_gap
        label = render_text(fonts["small"], str(s.get("label", "")), chrome.text_on_card_soft)
        surface.blit(label, (x, y))
        y += label.get_height()
        spark_rect = pygame.Rect(x, y, spark_w, spark_h)
        _draw_sparkline(surface, spark_rect, s, fonts["small"], chrome)
        y += spark_h


def _draw_sparkline(surface: pygame.Surface, rect: pygame.Rect, spec: dict, font: Any, chrome: Chrome) -> None:
    """A filled area chart of ``spec['values']`` with an optional threshold line."""
    values = [float(v) for v in spec.get("values", [])]
    pygame.draw.rect(surface, chrome.inset_dim, rect, border_radius=4)
    pygame.draw.rect(surface, chrome.inset_edge, rect, width=1, border_radius=4)
    if not values:
        return

    hi = float(spec.get("max", max(values) or 1))
    lo = float(spec.get("min", 0))
    span = max(1e-6, hi - lo)
    inset = 3
    plot = rect.inflate(-inset * 2, -inset * 2)

    def point(i: int, v: float) -> tuple[int, int]:
        n = max(1, len(values) - 1)
        px = plot.x + int(plot.width * (i / n))
        py = plot.bottom - int(plot.height * ((v - lo) / span))
        return px, max(plot.top, min(plot.bottom, py))

    pts = [point(i, v) for i, v in enumerate(values)]

    # threshold line (e.g. the sustainability limit) drawn behind the curve
    threshold = spec.get("threshold")
    if threshold is not None:
        ty = plot.bottom - int(plot.height * ((float(threshold) - lo) / span))
        ty = max(plot.top, min(plot.bottom, ty))
        for dash_x in range(plot.x, plot.right, 6):
            pygame.draw.line(surface, chrome.accent_deep, (dash_x, ty), (min(dash_x + 3, plot.right), ty))

    line_color = _series_color(spec)
    if len(pts) >= 2:
        fill = [(pts[0][0], plot.bottom), *pts, (pts[-1][0], plot.bottom)]
        area = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.polygon(area, (*line_color, 70), [(px - rect.x, py - rect.y) for px, py in fill])
        surface.blit(area, rect.topleft)
        pygame.draw.lines(surface, line_color, False, pts, 2)
    # mark the latest sample
    pygame.draw.circle(surface, line_color, pts[-1], 3)
    pygame.draw.circle(surface, chrome.text_on_card, pts[-1], 3, width=1)


def _series_color(spec: dict) -> tuple[int, int, int]:
    color = spec.get("color")
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        return (int(color[0]), int(color[1]), int(color[2]))
    return (70, 120, 150)          # pack WATER base — reads as "stock/level"


def _metrics_fonts(tile: int) -> dict[str, Any]:
    return {
        "title": get_font(max(9, int(tile * 0.52)), bold=True),
        "body": get_font(max(8, int(tile * 0.42))),
        "small": get_font(max(8, int(tile * 0.34))),
    }


def _anchor_rect(renderer: "Any", anchor: str, w: int, h: int) -> pygame.Rect:
    """Place the panel in a corner of the WORLD view (never over the side panels)."""
    margin = max(10, renderer.tile_size // 3)
    world_w, bottom = renderer.floor_surface.get_size()
    top = renderer.viewport_pad_n
    left = margin
    right = world_w - w - margin
    y_top = top + margin
    y_bottom = bottom - h - margin
    positions = {
        "top_left": (left, y_top),
        "top_right": (right, y_top),
        "bottom_left": (left, y_bottom),
        "bottom_right": (right, y_bottom),
    }
    x, y = positions.get(anchor, positions["top_left"])
    return pygame.Rect(int(x), int(y), int(w), int(h))
