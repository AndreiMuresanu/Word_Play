"""Dynamic behaviours: *activatable* visual states — the moving counterpart to
the static behaviours in ``behaviours.py``.

A static behaviour is always on (a lamp always glows). A dynamic behaviour is a
named state an entity can enter and leave — fishing, chopping, hunting, fleeing.
While it's active the renderer:

* swaps to the ``_<pose>`` sprite sibling if one exists (``carpenter`` →
  ``carpenter_chopping``), auto-animated by its own ``_2`` frame — the same
  filename convention as ``_2``/``_back``/``_glow``, so the behaviour never names a
  file itself;
* optionally locks facing (an angler faces the water);
* optionally shows a looping effect sprite a little ahead of the entity (the cast
  splash on the lake, the woodchips off an axe);
* optionally makes the whole sprite **recoil/tremble** (``shake``) — a struck
  sheep flinches, a hammered anvil buzzes, a panicked hen shivers;
* optionally throws a **punchy impact** the moment the effect lands (``impact``)
  — the burst pulses bright instead of sitting still, so a swing reads as a *hit*;
* optionally floats an **emote** above the entity (``emote``) — a red ``!`` of
  alarm, spikes of anger, a music note, sleepy ``z`` — the cheapest way to read
  a creature's mood at a glance and the thing that makes a scene feel *alive*.

Everything here is pure render data driven by ONE field the sim toggles — set
``renderable.action = "hunting"`` to enter the state, ``= None`` to leave. No new
components, no game logic: the drama is entirely in how the frame is drawn.

    Renderable(sprite_path="villager_guard")               # normal
    hunter.get_component(Renderable).action = "hunting"    # lunging + anger + impact
    sheep.get_component(Renderable).action  = "fleeing"    # shivering + red alarm
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dynamic_Behaviour:
    """One activatable visual state — all fields optional, all skipped if unset.

    ``pose`` names the sprite sibling to swap in while active (``"chopping"`` →
    ``<sprite>_chopping``). ``face`` pins facing to one of up/down/left/right.
    ``effect`` is a sprite-name for a looping VFX (auto-animated via its ``_2``
    frame) drawn ``effect_forward`` tiles ahead of the entity at ``effect_scale``;
    a negative ``effect_forward`` trails it behind (a wake, kicked-up dust).

    The three "juice" knobs make an activity read as an *interaction*:

    * ``shake`` — recoil amplitude as a fraction of a tile (~0.03 a working
      tremble, ~0.12 a panicked shiver / a real hit). The sprite jitters; its
      shadow stays put, so it reads as motion rather than teleporting.
    * ``impact`` — pulse the effect sprite bright-and-big on a fast beat, so the
      burst punches instead of idling (strikes, chops, sparks).
    * ``emote`` — a mood glyph floated above the entity. Known glyphs:
      ``alarm`` (red !), ``anger`` (red spikes), ``note`` (cyan ♪),
      ``sleep`` (pale z), ``love`` (pink heart), ``spark`` (gold star),
      ``sweat`` (blue drop). Unknown names fall back to a soft dot.
    """

    pose: str | None = None
    face: str | None = None
    effect: str | None = None
    effect_forward: float = 1.0
    effect_scale: float = 0.7
    shake: float = 0.0
    impact: bool = False
    emote: str | None = None


DYNAMIC_BEHAVIOURS: dict[str, Dynamic_Behaviour] = {}


def register_dynamic_behaviour(behaviour: Dynamic_Behaviour, *names: str) -> None:
    """Bind one dynamic behaviour to one or more names (last-registered wins)."""
    for name in names:
        DYNAMIC_BEHAVIOURS[name] = behaviour


def resolve_dynamic_behaviour(name: str | None) -> Dynamic_Behaviour | None:
    """Look up a dynamic behaviour by name, or ``None`` for unknown/blank."""
    if not name:
        return None
    return DYNAMIC_BEHAVIOURS.get(name)


# ══════════════════════════════════════════════════════════════════════════════
#  The interactive catalog — the exciting verbs of a living town.
# ══════════════════════════════════════════════════════════════════════════════
# Missing pose art falls back to the base sprite and missing effect sprites are
# skipped, so every one of these is safe to activate against any sprite — packs
# add the matching art later, the juice (shake/impact/emote) is always procedural.

# ── predator & prey: the heart of the drama ──────────────────────────────────
register_dynamic_behaviour(
    # a lunge: attack pose, a spark that punches forward, a jolt of recoil, fury
    Dynamic_Behaviour(pose="attacking", effect="spark", effect_forward=0.85,
                      effect_scale=0.6, shake=0.05, impact=True, emote="anger"),
    "hunting", "attacking", "striking", "lunging",
)
register_dynamic_behaviour(
    # the victim: violent shiver, a red ! of panic, chips of dust flying off
    Dynamic_Behaviour(effect="dust", effect_forward=-0.3, effect_scale=0.5,
                      shake=0.14, emote="alarm"),
    "hurt", "struck", "wounded",
)
register_dynamic_behaviour(
    # bolting away: a hard shiver, alarm, dust kicked up behind
    Dynamic_Behaviour(effect="dust", effect_forward=-0.5, effect_scale=0.45,
                      shake=0.1, emote="alarm"),
    "fleeing", "startled", "panicking", "spooked",
)
register_dynamic_behaviour(
    # a sheepdog / an alerted guard: barking, anger, a small forward puff
    Dynamic_Behaviour(effect="dust", effect_forward=0.6, effect_scale=0.4,
                      shake=0.05, emote="anger"),
    "barking", "herding", "chasing",
)
register_dynamic_behaviour(
    # a cat's coiled pounce: low shiver, gold spark, no emote (silent hunter)
    Dynamic_Behaviour(pose="attacking", effect="sparkle", effect_forward=0.7,
                      effect_scale=0.5, shake=0.06, impact=True),
    "pouncing", "stalking",
)
register_dynamic_behaviour(
    # peaceful grazing / nibbling: the faintest idle bob, no drama
    Dynamic_Behaviour(shake=0.015),
    "grazing", "nibbling", "pecking",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(emote="alarm", shake=0.05),
    "alerting", "watchful",
)

# ── the logging camp: felling a grove ─────────────────────────────────────────
register_dynamic_behaviour(
    # the axe: chopping pose, woodchips (dust) punching off the swing, a work-jolt
    Dynamic_Behaviour(pose="chopping", effect="dust", effect_forward=0.6,
                      effect_scale=0.5, shake=0.04, impact=True),
    "chopping", "cutting", "felling",
)
register_dynamic_behaviour(
    # the tree taking the hit: a heavy tremble in place (no pose, no emote)
    Dynamic_Behaviour(shake=0.05),
    "shaking", "trembling", "toppling",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="mining", effect="sparkle", effect_forward=0.7,
                      effect_scale=0.5, shake=0.04, impact=True),
    "mining", "digging",
)

# ── the smithy & workshops: sparks fly ───────────────────────────────────────
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="repairing", effect="spark", effect_forward=0.5,
                      effect_scale=0.5, shake=0.05, impact=True),
    "repairing", "hammering", "forging",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="working", shake=0.02),
    "working", "operating", "crafting",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="mixing", effect="bubbles", effect_forward=0.4, effect_scale=0.45),
    "mixing",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="scanning", effect="beam", effect_forward=0.8, effect_scale=0.55),
    "scanning",
)

# ── the kitchen, farm & plaza chores ─────────────────────────────────────────
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="cooking", effect="steam", effect_forward=0.4, effect_scale=0.5),
    "cooking",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="cleaning", face="down", effect="dust", effect_forward=0.6, effect_scale=0.45),
    "cleaning", "scrubbing",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="sweeping", effect="dust", effect_forward=0.5, effect_scale=0.45, shake=0.02),
    "sweeping",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="planting", face="down"),
    "planting", "sowing",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="harvesting", effect="sparkle", effect_forward=0.6, effect_scale=0.45),
    "harvesting", "picking", "foraging",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="watering", face="down", effect="water_drops", effect_forward=0.7, effect_scale=0.45),
    "watering",
)

# ── the lake ─────────────────────────────────────────────────────────────────
# an angler: rod pose facing the water, a cast splash a tile ahead on the surface
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="fishing", face="up", effect="catch_splash", effect_forward=1.0),
    "fishing", "angling",
)
register_dynamic_behaviour(
    # the wake trails BEHIND the boat (negative forward)
    Dynamic_Behaviour(pose="rowing", effect="splash", effect_forward=-0.6, effect_scale=0.5),
    "rowing", "paddling",
)

# ── carrying, play & rest ────────────────────────────────────────────────────
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="carrying"),
    "carrying", "hauling",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="celebrating", face="down", emote="note", shake=0.03),
    "celebrating", "cheering", "playing", "dancing",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(emote="love"),
    "smitten", "loving",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="sitting"),
    "sitting",
)
register_dynamic_behaviour(
    Dynamic_Behaviour(pose="sleeping", emote="sleep"),
    "sleeping", "resting", "napping",
)
