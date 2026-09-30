"""Switchable UI chrome: every panel/text color the renderer draws, as a preset.

The world is rendered from a sprite pack; the *chrome* is everything around it —
HUD, sidebar, terminal, inspector card, speech bubbles, metrics panel, end
overlay. A ``Chrome`` is a named palette + painter style; themes select one via ``theme.json``'s
``"chrome"`` key, or pass ``Pygame_Renderer(..., chrome="slate")`` directly.
Everything stays procedural — no UI art is required by any pack.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import pygame

RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Chrome:
    name: str
    # window / world backdrop
    backdrop: RGB
    # large fixed panels (HUD, sidebar)
    panel: RGB
    panel_edge: RGB                 # ink seam where a panel meets the world
    panel_edge_hi: RGB              # lit bevel next to the seam
    # sunken sheet set into a panel (transcript, input box, log)
    inset_dim: RGB
    inset_edge: RGB
    # floating card (inspector, end overlay, metrics)
    card: RGB
    card_edge: RGB
    # text
    text_on_card: RGB
    text_on_card_soft: RGB
    text_on_panel: RGB
    text_on_panel_dim: RGB
    # accents
    accent: RGB                     # headers, highlights
    accent_deep: RGB                # borders, pins, prompts
    selection: RGB                  # selection ring
    focus: RGB                      # camera-follow ring
    # speech bubbles
    bubble_fill: RGB
    bubble_edge: RGB
    bubble_text: RGB
    # terminal panel
    term_bg: RGB
    term_edge: RGB
    term_edge_soft: RGB
    term_text: RGB
    term_text_dim: RGB
    term_text_soft: RGB
    term_text_faint: RGB
    term_input_bg: RGB
    term_input_edge: RGB
    term_input_text: RGB
    term_inset: RGB
    term_inset_edge: RGB
    term_transcript_text: RGB
    term_track: RGB
    term_thumb: RGB
    # painter style switches
    corner_style: str = "pins"      # "pins" | "none"
    panel_texture: str = "grain"    # "grain" | "flat"
    radius_scale: float = 1.0

    # ── panel painters (style-branched, shared implementation) ────────────────

    def draw_panel(self, surface: pygame.Surface, rect: pygame.Rect, *, edge_left: bool = False, edge_top: bool = False) -> None:
        """A flat slab for large fixed panels (terminal, HUD, sidebar)."""
        pygame.draw.rect(surface, self.panel, rect)
        if self.panel_texture == "grain":
            # faint plank grain: a few darker horizontal seams, deterministic
            seam = tuple(max(0, c - 9) for c in self.panel)
            for y in range(rect.top + 22, rect.bottom, 46):
                pygame.draw.line(surface, seam, (rect.left + 4, y), (rect.right - 4, y))
        if edge_left:
            pygame.draw.line(surface, self.panel_edge, rect.topleft, rect.bottomleft, 2)
            pygame.draw.line(surface, self.panel_edge_hi, (rect.left + 2, rect.top), (rect.left + 2, rect.bottom))
        if edge_top:
            pygame.draw.line(surface, self.panel_edge, rect.topleft, rect.topright, 2)
            pygame.draw.line(surface, self.panel_edge_hi, (rect.left, rect.top + 2), (rect.right, rect.top + 2))

    def draw_card(self, surface: pygame.Surface, rect: pygame.Rect, *, radius: int = 10) -> None:
        """A raised floating card (inspector card, metrics, end overlay)."""
        radius = max(2, int(radius * self.radius_scale))
        pygame.draw.rect(surface, self.card, rect, border_radius=radius)
        pygame.draw.rect(surface, self.card_edge, rect, width=2, border_radius=radius)
        if self.corner_style == "pins":
            pin = 3
            for cx, cy in (
                (rect.left + 7, rect.top + 7),
                (rect.right - 8, rect.top + 7),
                (rect.left + 7, rect.bottom - 8),
                (rect.right - 8, rect.bottom - 8),
            ):
                pygame.draw.circle(surface, self.accent_deep, (cx, cy), pin)
                pygame.draw.circle(surface, self.accent, (cx - 1, cy - 1), 1)


# ── shipped chrome styles ──────────────────────────────────────────────────────

# The dark terminal palette shared by the rustic and slate chromes.
_DARK_TERMINAL: dict[str, RGB] = dict(
    term_bg=(10, 13, 18),
    term_edge=(52, 63, 79),
    term_edge_soft=(44, 56, 74),
    term_text=(245, 247, 250),
    term_text_dim=(145, 169, 194),
    term_text_soft=(153, 163, 178),
    term_text_faint=(124, 136, 154),
    term_input_bg=(13, 16, 22),
    term_input_edge=(88, 102, 126),
    term_input_text=(232, 236, 243),
    term_inset=(14, 18, 26),
    term_inset_edge=(42, 50, 66),
    term_transcript_text=(207, 214, 224),
    term_track=(36, 44, 58),
    term_thumb=(128, 203, 255),
)


# The original wood-and-parchment town chrome; the default everywhere.
RUSTIC = Chrome(
    name="rustic",
    backdrop=(24, 19, 22),
    panel=(56, 40, 32),
    panel_edge=(43, 36, 48),
    panel_edge_hi=(134, 96, 62),
    inset_dim=(225, 210, 180),
    inset_edge=(196, 176, 142),
    card=(238, 226, 200),
    card_edge=(43, 36, 48),
    text_on_card=(58, 46, 40),
    text_on_card_soft=(108, 88, 72),
    text_on_panel=(240, 230, 208),
    text_on_panel_dim=(196, 176, 150),
    accent=(226, 180, 88),
    accent_deep=(176, 130, 62),
    selection=(166, 196, 138),
    focus=(245, 214, 102),
    bubble_fill=(250, 245, 233),
    bubble_edge=(56, 46, 39),
    bubble_text=(18, 16, 14),
    **_DARK_TERMINAL,
    corner_style="pins",
    panel_texture="grain",
)

# Dark instrumentation chrome for sci-fi / lab / factory environments — the
# terminal's slate-and-cyan family extended to every panel.
SLATE = Chrome(
    name="slate",
    backdrop=(12, 14, 18),
    panel=(24, 28, 35),
    panel_edge=(10, 12, 16),
    panel_edge_hi=(52, 60, 72),
    inset_dim=(15, 18, 23),
    inset_edge=(38, 45, 56),
    card=(228, 233, 238),
    card_edge=(52, 60, 72),
    text_on_card=(30, 36, 44),
    text_on_card_soft=(96, 108, 122),
    text_on_panel=(218, 226, 235),
    text_on_panel_dim=(140, 152, 168),
    accent=(96, 200, 224),
    accent_deep=(58, 140, 168),
    selection=(120, 224, 190),
    focus=(255, 214, 102),
    bubble_fill=(232, 238, 244),
    bubble_edge=(40, 48, 60),
    bubble_text=(22, 28, 36),
    **_DARK_TERMINAL,
    corner_style="none",
    panel_texture="flat",
)

# Light neutral chrome for abstract / econ / whiteboard-style environments.
MINIMAL = Chrome(
    name="minimal",
    backdrop=(232, 231, 228),
    panel=(246, 245, 242),
    panel_edge=(200, 199, 194),
    panel_edge_hi=(255, 255, 255),
    inset_dim=(248, 247, 244),
    inset_edge=(222, 221, 216),
    card=(255, 255, 255),
    card_edge=(206, 206, 200),
    text_on_card=(42, 46, 52),
    text_on_card_soft=(120, 126, 134),
    text_on_panel=(42, 46, 52),
    text_on_panel_dim=(130, 136, 144),
    accent=(196, 138, 42),
    accent_deep=(150, 102, 28),
    selection=(90, 140, 196),
    focus=(196, 138, 42),
    bubble_fill=(255, 255, 255),
    bubble_edge=(120, 126, 134),
    bubble_text=(42, 46, 52),
    term_bg=(246, 245, 242),
    term_edge=(200, 199, 194),
    term_edge_soft=(214, 213, 208),
    term_text=(42, 46, 52),
    term_text_dim=(130, 136, 144),
    term_text_soft=(140, 146, 154),
    term_text_faint=(168, 172, 178),
    term_input_bg=(255, 255, 255),
    term_input_edge=(200, 199, 194),
    term_input_text=(42, 46, 52),
    term_inset=(252, 251, 248),
    term_inset_edge=(222, 221, 216),
    term_transcript_text=(60, 66, 74),
    term_track=(228, 227, 222),
    term_thumb=(150, 102, 28),
    corner_style="none",
    panel_texture="flat",
    radius_scale=1.2,
)

CHROMES: dict[str, Chrome] = {
    "rustic": RUSTIC,
    "slate": SLATE,
    "minimal": MINIMAL,
}

_warned_unknown: set[str] = set()


def resolve_chrome(name: "str | Chrome | None") -> Chrome:
    """Resolve a chrome by instance or registry name; unknown names warn once
    and fall back to rustic (the sim keeps running)."""
    if isinstance(name, Chrome):
        return name
    if name is None:
        return RUSTIC
    chrome = CHROMES.get(name)
    if chrome is not None:
        return chrome
    if name not in _warned_unknown:
        _warned_unknown.add(name)
        print(
            f"[word_play] unknown chrome {name!r} — using 'rustic'. Available: {sorted(CHROMES)}",
            file=sys.stderr,
        )
    return RUSTIC


def active_chrome(renderer: Any) -> Chrome:
    return renderer.chrome_theme
