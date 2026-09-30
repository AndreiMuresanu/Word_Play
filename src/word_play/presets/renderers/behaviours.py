"""Render behaviours: named bundles of *rendering behaviour* — not sprites.

A behaviour answers "how does this thing behave on screen?" — does it cast
light, send up smoke/steam, sit in the ground layer as walk-on terrain, flicker
like fire? It never decides *which* sprite is drawn; that is always
``sprite_path`` (a literal path, or a theme sprite-name the active theme
resolves to a file).

    Renderable(sprite_path="lamp",   behaviour="light")    # a lamp that glows
    Renderable(sprite_path="oven",   behaviour="oven")     # glows AND steams
    Renderable(sprite_path="dock",   behaviour="floor")    # walk-on terrain
    Renderable(sprite_path="rune.png", behaviour="magic")  # literal sprite, cool glow

Behaviours are theme-independent: ``behaviour="light"`` shines the same in every
pack. The registry below ships general presets covering the common cases; add
your own with :func:`register_behaviour` (see BEHAVIOURS.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Render_Behaviour:
    """One behaviour preset. Every field maps to a general renderer primitive.

    ``glow`` is an RGB light colour (``glow_radius`` in tiles, ``glow_strength``
    where 1.0 is a standard lamp); ``flicker`` (0..~0.3) wavers that light like
    a flame. ``smoke`` sends up a soft drift (chimneys, stoves, steam). ``floor``
    draws the sprite as walk-on ground terrain (ground layer, no shadow, agents
    stand centred on top). Fields left at their defaults do nothing.
    """

    glow: tuple[int, int, int] | None = None
    glow_radius: float = 1.7
    glow_strength: float = 1.0
    flicker: float = 0.0
    smoke: bool = False
    floor: bool = False


# ── the preset registry ───────────────────────────────────────────────────────
# Keyed by behaviour name; several names can share one behaviour (aliases). Glow
# values are tuned to read at dusk/night without blowing out at 1x zoom.
RENDER_BEHAVIOURS: dict[str, Render_Behaviour] = {}


def register_behaviour(behaviour: Render_Behaviour, *names: str) -> None:
    """Bind one behaviour to one or more names (the last-registered wins)."""
    for name in names:
        RENDER_BEHAVIOURS[name] = behaviour


def resolve_behaviour(name: str | None) -> Render_Behaviour | None:
    """Look up a behaviour by name, or ``None`` for an unknown/blank name."""
    if not name:
        return None
    return RENDER_BEHAVIOURS.get(name)


# warm light sources ──────────────────────────────────────────────────────────
register_behaviour(Render_Behaviour(glow=(255, 196, 132), glow_radius=2.2, glow_strength=1.0),
                   "light", "glow", "lit")
register_behaviour(Render_Behaviour(glow=(255, 190, 110), glow_radius=2.8, glow_strength=1.0),
                   "lamp", "streetlamp", "lantern", "sconce")
register_behaviour(Render_Behaviour(glow=(255, 202, 150), glow_radius=1.1, glow_strength=0.7, flicker=0.10),
                   "candle", "candlelight")
register_behaviour(Render_Behaviour(glow=(255, 206, 150), glow_radius=1.4, glow_strength=0.9),
                   "window", "lit_window", "hearthlight")
register_behaviour(Render_Behaviour(glow=(150, 104, 62), glow_radius=1.4, glow_strength=1.0),
                   "doorway", "door_glow")

# fire & hearths (glow + flicker, often smoke) ─────────────────────────────────
register_behaviour(Render_Behaviour(glow=(240, 150, 80), glow_radius=2.4, glow_strength=1.15,
                                    flicker=0.12, smoke=True),
                   "hearth", "fireplace")
register_behaviour(Render_Behaviour(glow=(210, 126, 62), glow_radius=2.2, glow_strength=1.2,
                                    flicker=0.06, smoke=True),
                   "stove", "oven", "kiln")
register_behaviour(Render_Behaviour(glow=(255, 140, 60), glow_radius=2.2, glow_strength=1.3,
                                    flicker=0.15, smoke=True),
                   "forge", "furnace")
register_behaviour(Render_Behaviour(glow=(255, 150, 70), glow_radius=1.8, glow_strength=1.0, flicker=0.20),
                   "torch", "brazier")
register_behaviour(Render_Behaviour(glow=(255, 140, 60), glow_radius=2.6, glow_strength=1.25,
                                    flicker=0.22, smoke=True),
                   "campfire", "bonfire", "fire")
register_behaviour(Render_Behaviour(glow=(255, 90, 50), glow_radius=1.6, glow_strength=1.1, flicker=0.10),
                   "ember", "coals", "lava", "magma")

# cool / magical light ─────────────────────────────────────────────────────────
register_behaviour(Render_Behaviour(glow=(150, 180, 230), glow_radius=2.2, glow_strength=0.9),
                   "cool_light", "moonlight")
register_behaviour(Render_Behaviour(glow=(130, 180, 240), glow_radius=1.8, glow_strength=1.0, flicker=0.08),
                   "crystal", "rune", "magic", "arcane")
register_behaviour(Render_Behaviour(glow=(110, 156, 215), glow_radius=1.5, glow_strength=1.0),
                   "water_glow", "fountain", "shimmer")
register_behaviour(Render_Behaviour(glow=(170, 120, 240), glow_radius=2.2, glow_strength=1.15, flicker=0.15),
                   "portal", "vortex")

# smoke / steam only (no light) ────────────────────────────────────────────────
register_behaviour(Render_Behaviour(smoke=True), "chimney", "smoke", "steam", "vent")

# walk-on ground terrain ───────────────────────────────────────────────────────
register_behaviour(Render_Behaviour(floor=True),
                   "floor", "bridge", "deck", "boardwalk", "rug", "road", "carpet", "platform")


def apply_behaviour(renderable) -> None:
    """Fill a Renderable's behaviour fields from its ``behaviour`` preset.

    Explicit values always win: a ``Renderable(glow=...)`` keeps its colour, and
    the behaviour only supplies what the author left unset. Sprites are never
    touched.
    """
    behaviour = resolve_behaviour(renderable.behaviour)
    if behaviour is None:
        return
    if behaviour.glow is not None and renderable.glow is None:
        renderable.glow = behaviour.glow
        renderable.glow_radius = behaviour.glow_radius
        renderable.glow_strength = behaviour.glow_strength
    if behaviour.flicker and not renderable.flicker:
        renderable.flicker = behaviour.flicker
    if behaviour.smoke:
        renderable.smoke = True
    if behaviour.floor:
        renderable.floor = True
