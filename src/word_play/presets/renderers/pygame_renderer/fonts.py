"""Process-wide font registry and rendered-text caches.

``pygame.font.SysFont`` construction runs font matching (expensive) and
``font.render`` re-rasterizes identical strings — both used to run every
frame. Fonts returned by :func:`get_font` live until :func:`reset_font_caches`
(run on pygame init), so surfaces cached by ``(font, text, color)`` can
never go stale.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import pygame

_FONTS: dict[tuple[int, bool], Any] = {}
_TEXT: OrderedDict = OrderedDict()
_WRAP: OrderedDict = OrderedDict()
_TEXT_CAP = 4096
_WRAP_CAP = 4096


def reset_font_caches() -> None:
    """Drop fonts and rendered text; call after ``pygame.quit()``/re-init.

    Font objects die with the font module, so a renderer created after
    ``replay()`` quit pygame must not be handed the stale ones back.
    """
    _FONTS.clear()
    _TEXT.clear()
    _WRAP.clear()


def get_font(size: int, *, bold: bool = False) -> Any:
    """Return a shared SysFont for ``size``/``bold``, building it at most once."""
    key = (int(size), bool(bold))
    font = _FONTS.get(key)
    if font is None:
        font = pygame.font.SysFont(None, int(size), bold=bold)
        _FONTS[key] = font
    return font


def render_text(font: Any, text: str, color: tuple) -> Any:
    """``font.render`` with an LRU cache keyed by (font, text, color)."""
    key = (id(font), text, tuple(color))
    surface = _TEXT.get(key)
    if surface is None:
        surface = font.render(text, True, color)
        _TEXT[key] = surface
        if len(_TEXT) > _TEXT_CAP:
            _TEXT.popitem(last=False)
    else:
        _TEXT.move_to_end(key)
    return surface


def wrap_text_lines(font: Any, text: str, max_width: int) -> list[str]:
    """Wrap text greedily into lines that fit within ``max_width`` (cached).

    The greedy fit calls ``font.size`` per word, which adds up when panels
    re-wrap a whole transcript every frame; results are memoized per
    (font, text, width). A fresh list is returned so callers may mutate it.
    """
    key = (id(font), text, int(max_width))
    cached = _WRAP.get(key)
    if cached is None:
        words = text.split()
        if not words:
            cached = ("",)
        else:
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
            cached = tuple(lines)
        _WRAP[key] = cached
        if len(_WRAP) > _WRAP_CAP:
            _WRAP.popitem(last=False)
    else:
        _WRAP.move_to_end(key)
    return list(cached)
