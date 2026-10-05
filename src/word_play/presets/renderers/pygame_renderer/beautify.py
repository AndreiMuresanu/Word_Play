"""Zero-authoring beautification pipeline for the pygame renderer.

Every sprite the renderer loads flows through :func:`harmonize_surface`, and every
free-standing entity can request a :func:`build_soft_shadow`. Both operate purely on
pixel data using stock pygame (no extra dependencies), so environments need no extra
authoring and no new art to look cohesive.

The single biggest problem with a sprite library assembled from many packs (DawnLike,
CDDA, Pokemon-era tiles, Mana Seed characters, ...) is that each pack carries its own
white balance and saturation. Desaturating slightly and casting every sprite toward one
shared tint at load time is what turns that mishmash into something that reads as
"designed".
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True, slots=True)
class Mood:
    """A named atmosphere: load-time grade + runtime ambient light, as one preset.

    ``saturation``/``tint`` grade sprites when they load; the ambient fields and
    ``light_level`` drive the per-frame lighting pass. ``light_level`` is the
    darkness factor (0 = broad daylight, 1 = deep night) that scales lamp glows
    and ``_glow`` emissive sprites, so lights fade in exactly as the world dims.
    """

    saturation: float = 0.94
    tint: tuple[float, float, float] = (1.0, 0.99, 0.95)
    ambient_rgba: tuple[int, int, int, int] | None = None
    ambient_rgba_bottom: tuple[int, int, int, int] | None = None
    ambient_mult: tuple[int, int, int] | None = None
    light_level: float = 0.0


MOODS: dict[str, Mood] = {
    "day": Mood(),
    "morning": Mood(
        saturation=0.96,
        tint=(1.0, 1.0, 0.97),
        ambient_rgba=(255, 220, 160, 26),
        ambient_mult=(255, 240, 220),
        light_level=0.15,
    ),
    "dusk": Mood(
        saturation=0.86,
        tint=(1.0, 0.93, 0.84),
        ambient_rgba=(255, 160, 70, 46),
        ambient_rgba_bottom=(205, 110, 145, 42),
        ambient_mult=(235, 190, 160),
        light_level=0.65,
    ),
    "night": Mood(
        saturation=0.80,
        tint=(0.92, 0.95, 1.0),
        # a lighter blue wash and a less blue multiply keep lamp pools warm
        # (R > B inside the pool) while the far ambient stays moonlit
        ambient_rgba=(24, 36, 88, 26),
        ambient_mult=(108, 112, 150),
        light_level=1.0,
    ),
    "rain": Mood(
        saturation=0.74,
        tint=(0.94, 0.97, 1.0),
        ambient_rgba=(80, 100, 130, 38),
        ambient_mult=(180, 190, 205),
        light_level=0.45,
    ),
}

# Day/night keyframes (0.0 = midnight, wraps). Only ambient fields lerp, so sprite caches never thrash.
DAY_CYCLE: list[tuple[float, str]] = [
    (0.00, "night"),
    (0.22, "night"),
    (0.30, "morning"),
    (0.40, "day"),
    (0.62, "day"),
    (0.74, "dusk"),
    (0.84, "night"),
    (1.00, "night"),
]


@dataclass(slots=True)
class Beautify_Config:
    """Tunable, all-optional beautification parameters.

    Defaults are intentionally subtle: enough to unify clashing palettes without
    visibly "filtering" the art. Set ``enabled = False`` to bypass the whole pipeline.
    """

    enabled: bool = True

    grade_enabled: bool = True
    # Fraction of saturation kept (1.0 = untouched).
    saturation: float = 0.82
    # Per-channel multiply on every sprite (<=1.0); a shared cast unifies packs.
    tint: tuple[float, float, float] = (1.0, 0.98, 0.92)
    # Flat brightness lift after grading (0-255).
    brighten: int = 6

    # Paths containing these skip grading (UI, chat, `_glow` overlays).
    grade_skip_fragments: tuple[str, ...] = ("/ui/", "\\ui\\", "chat_interface", "_glow.png")

    # Dark rim around characters and props; tiles are always skipped.
    outline_enabled: bool = False
    outline_color: tuple[int, int, int] = (26, 22, 30)
    outline_alpha: int = 210
    outline_skip_fragments: tuple[str, ...] = (
        "/ui/", "chat_interface", "floor", "wall", "trail", "ground", "water", "carpet",
    )

    shadow_enabled: bool = True
    shadow_alpha: int = 90        # peak opacity of the cast shadow
    shadow_squash: float = 0.34   # vertical height as a fraction of the sprite
    shadow_scale: float = 0.92    # horizontal width relative to sprite width

    # Glide between tiles, paced to the observed step rate.
    smooth_movement: bool = True

    # foo.png + foo_2.png animate automatically, with per-entity phase offsets.
    animate: bool = True
    animation_period: float = 0.55  # seconds per frame
    # Item sprites often use ``_2`` for variants rather than frames — skip them.
    animate_skip_fragments: tuple[str, ...] = ("/items/", "\\items\\")

    # RGBA wash over the world, usually set via a mood. None = plain day.
    ambient_rgba: tuple[int, int, int, int] | None = None
    # Multiply applied before the wash so lamp glow can carve light out of the dark.
    ambient_mult: tuple[int, int, int] | None = None
    # Optional bottom wash colour; makes the wash a vertical gradient.
    ambient_rgba_bottom: tuple[int, int, int, int] | None = None
    # Drifting motes drawn while an ambient wash is active.
    particles: bool = True
    particle_color: tuple[int, int, int] = (255, 214, 130)

    # 0 = day, 1 = deep night; scales lamp and `_glow` strength.
    light_level: float = 0.0
    # Normalized clock (0 = midnight, wraps); when set, overrides the ambient fields each frame.
    time_of_day: float | None = None


def apply_mood(config: Beautify_Config, mood: "str | Mood") -> None:
    """Apply an atmosphere preset to a config (grade + ambient + light level).

    The grade fields (saturation/tint) act at image-load time, so call this
    before rendering starts — switching later regrades only newly loaded sprites.
    """
    if isinstance(mood, str):
        try:
            mood = MOODS[mood]
        except KeyError:
            raise KeyError(f"Unknown mood {mood!r}. Available: {sorted(MOODS)}") from None
    config.saturation = mood.saturation
    config.tint = mood.tint
    config.ambient_rgba = mood.ambient_rgba
    config.ambient_rgba_bottom = mood.ambient_rgba_bottom
    config.ambient_mult = mood.ambient_mult
    config.light_level = mood.light_level


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _lerp_rgba(
    a: tuple[int, ...] | None,
    b: tuple[int, ...] | None,
    f: float,
) -> tuple[int, ...] | None:
    """Lerp two washes; None means "absent" (same hue, zero alpha)."""
    if a is None and b is None:
        return None
    if a is None:
        a = (*b[:3], 0)
    if b is None:
        b = (*a[:3], 0)
    return tuple(int(round(_lerp(x, y, f))) for x, y in zip(a, b))


def _lerp_mult(
    a: tuple[int, int, int] | None,
    b: tuple[int, int, int] | None,
    f: float,
) -> tuple[int, int, int] | None:
    """Lerp two multiply colors; None means "no darkening" (pure white)."""
    if a is None and b is None:
        return None
    a = a or (255, 255, 255)
    b = b or (255, 255, 255)
    return tuple(int(round(_lerp(x, y, f))) for x, y in zip(a, b))


def resolve_ambient(
    config: Beautify_Config,
) -> tuple[
    tuple[int, int, int, int] | None,
    tuple[int, int, int, int] | None,
    tuple[int, int, int] | None,
    float,
]:
    """The frame's effective (wash, wash_bottom, mult, light_level).

    Static configs pass through unchanged; a set ``time_of_day`` lerps the
    ambient fields between the DAY_CYCLE keyframe moods instead.
    """
    t = config.time_of_day
    if t is None:
        return (
            config.ambient_rgba,
            config.ambient_rgba_bottom,
            config.ambient_mult,
            max(0.0, min(1.0, config.light_level)),
        )

    t = t % 1.0
    prev_t, prev_name = DAY_CYCLE[0]
    for key_t, name in DAY_CYCLE[1:]:
        if t <= key_t:
            span = key_t - prev_t
            f = 0.0 if span <= 0 else (t - prev_t) / span
            a, b = MOODS[prev_name], MOODS[name]
            # a missing bottom means "flat wash" (bottom == top), not "no wash" —
            # lerping toward zero alpha here would pop at the next keyframe
            a_bottom = a.ambient_rgba_bottom if a.ambient_rgba_bottom is not None else a.ambient_rgba
            b_bottom = b.ambient_rgba_bottom if b.ambient_rgba_bottom is not None else b.ambient_rgba
            return (
                _lerp_rgba(a.ambient_rgba, b.ambient_rgba, f),
                _lerp_rgba(a_bottom, b_bottom, f),
                _lerp_mult(a.ambient_mult, b.ambient_mult, f),
                _lerp(a.light_level, b.light_level, f),
            )
        prev_t, prev_name = key_t, name
    last = MOODS[DAY_CYCLE[-1][1]]
    return last.ambient_rgba, last.ambient_rgba_bottom, last.ambient_mult, last.light_level


def _skip_grade(sprite_name: str, config: Beautify_Config) -> bool:
    lowered = sprite_name.lower()
    return any(fragment in lowered for fragment in config.grade_skip_fragments)


def harmonize_surface(surface: pygame.Surface, sprite_name: str, config: Beautify_Config) -> pygame.Surface:
    """Return a color-graded copy of ``surface`` unified toward the shared mood.

    Per-pixel alpha is preserved (BLEND_RGB_* flags never touch the alpha channel).
    """
    if not config.enabled or not config.grade_enabled or _skip_grade(sprite_name, config):
        return surface

    graded = surface.copy()

    # Desaturate toward greyscale by overlaying a translucent grey version.
    if config.saturation < 1.0:
        grey = pygame.transform.grayscale(surface)
        grey.set_alpha(int((1.0 - config.saturation) * 255))
        graded.blit(grey, (0, 0))

    r, g, b = config.tint
    if (r, g, b) != (1.0, 1.0, 1.0):
        graded.fill(
            (int(r * 255), int(g * 255), int(b * 255), 255),
            special_flags=pygame.BLEND_RGB_MULT,
        )

    if config.brighten:
        graded.fill(
            (config.brighten, config.brighten, config.brighten, 0),
            special_flags=pygame.BLEND_RGB_ADD,
        )

    graded = _apply_outline(graded, sprite_name, config)
    return graded


def _apply_outline(surface: pygame.Surface, sprite_name: str, config: Beautify_Config) -> pygame.Surface:
    """Composite a consistent dark rim behind a sprite's silhouette (props only)."""
    lowered = sprite_name.lower()
    if not config.outline_enabled or any(f in lowered for f in config.outline_skip_fragments):
        return surface

    width, height = surface.get_size()
    mask = pygame.mask.from_surface(surface, 96)
    if mask.count() == 0:
        return surface

    rim = mask.to_surface(
        setcolor=(*config.outline_color, config.outline_alpha),
        unsetcolor=(0, 0, 0, 0),
    )
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    # Stamp the silhouette in the 4 cardinal directions to form a 1px border, then
    # lay the real sprite on top so only the protruding rim shows.
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out.blit(rim, (dx, dy))
    out.blit(surface, (0, 0))
    return out


def build_soft_shadow(image: pygame.Surface, config: Beautify_Config) -> pygame.Surface | None:
    """Derive a soft, squashed contact shadow from a sprite's silhouette.

    Uses the sprite's own alpha mask so the shadow matches the actual shape, then
    squashes and cheaply blurs it (downscale/upscale). Returns ``None`` if disabled.
    """
    if not config.enabled or not config.shadow_enabled:
        return None

    width, height = image.get_size()
    shadow_w = max(4, int(width * config.shadow_scale))
    shadow_h = max(4, int(height * config.shadow_squash))

    mask = pygame.mask.from_surface(image, 24)
    silhouette = mask.to_surface(
        setcolor=(0, 0, 0, config.shadow_alpha),
        unsetcolor=(0, 0, 0, 0),
    )

    squashed = pygame.transform.smoothscale(silhouette, (shadow_w, shadow_h))
    # Cheap blur: shrink then grow so the silhouette edges bleed softly.
    small = pygame.transform.smoothscale(squashed, (max(2, shadow_w // 3), max(2, shadow_h // 3)))
    return pygame.transform.smoothscale(small, (shadow_w, shadow_h))
