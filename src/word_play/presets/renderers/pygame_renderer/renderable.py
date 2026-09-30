from __future__ import annotations

from word_play.core.components import Component


class Renderable(Component):
    """Pygame sprite metadata for an entity.

    Two orthogonal knobs:

    * ``sprite_path`` — WHICH sprite. A literal path (``"a/b.png"``) or a bare
      sprite-name (``"tree"``, ``"villager_baker"``, ``"dock"``) that the renderer
      resolves at draw time (active theme first, then the library-wide index).
      The renderer never rewrites it. This is the only thing that picks pixels.
    * ``behaviour`` — HOW it behaves on screen: a behaviour preset from the
      general registry in ``word_play.presets.renderers.behaviours`` (e.g.
      ``"light"`` shines, ``"oven"`` glows and steams, ``"floor"`` is walk-on
      ground terrain, ``"campfire"`` flickers). Theme-independent; never a sprite.

    Behaviour fills in (all also settable directly, and explicit wins):
    ``glow`` (RGB light), ``glow_radius``/``glow_strength``, ``flicker`` (flame
    waver), ``smoke`` (drift of smoke/steam), and ``floor``. ``floor=True`` draws
    the sprite in the ground layer with no shadow and lets an agent stand centred
    on top instead of being shoved side-by-side — the clean way to lay terrain an
    agent occupies (docks, bridges, rugs) without multi-gridding it.
    """

    def __init__(
        self,
        sprite_path: str,
        z_index: int = 0,
        visible: bool = True,
        overlay_sprite: str | None = None,
        overlay_mode: str = "badge",
        overlay_scale: float | None = None,
        wall_set: str | None = None,
        behaviour: str | None = None,
        glow: tuple[int, int, int] | None = None,
        glow_radius: float = 1.7,
        glow_strength: float = 1.0,
        flicker: float = 0.0,
        smoke: bool = False,
        floor: bool = False,
        tint: tuple[int, int, int] | None = None,
        tint_strength: float = 0.55,
    ):
        super().__init__()
        self.sprite_path = sprite_path
        self.behaviour = behaviour          # behaviour preset (see behaviours.py)
        self.glow = glow  # RGB light color; composited when the scene has ambient
        self.glow_radius = glow_radius      # in tiles
        self.glow_strength = glow_strength  # 1.0 = standard lamp
        self.flicker = flicker              # 0 = steady; ~0.2 = flame waver
        self.smoke = smoke                  # send up a drift of smoke/steam
        self.wall_set = wall_set
        self.z_index = z_index
        self.visible = visible
        self.floor = floor  # walk-on ground detail: floor layer, no shadow, no stacking
        self.overlay_sprite = overlay_sprite
        self.overlay_mode = overlay_mode
        self.overlay_scale = overlay_scale
        # team/ownership recolor: multiply the sprite toward `tint` (preserves
        # the ink outline). One field covers CTF teams, coin ownership, berry
        # colors, gem grades — no per-variant art needed.
        self.tint = tint
        self.tint_strength = tint_strength

