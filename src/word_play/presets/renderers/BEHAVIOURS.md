# Render Behaviours — how it renders, not which sprite

A `Renderable` has two orthogonal knobs. Keep them straight and everything else
falls out:

| Knob | Question it answers | Example |
| --- | --- | --- |
| `sprite_path` | **WHICH** sprite is drawn | `"villager_baker"`, `"dock"`, `"a/b.png"` |
| `behaviour` | **HOW** it renders — always on | `"lamp"`, `"stove"`, `"floor"`, `"campfire"` |
| `action` | a **dynamic** state it can enter/leave | `"fishing"` (see below) |

```python
Renderable(sprite_path="lamp",  behaviour="light")    # a lamp sprite that shines
Renderable(sprite_path="oven",  behaviour="oven")     # glows AND sends up steam
Renderable(sprite_path="dock",  behaviour="floor")    # walk-on ground terrain
Renderable(sprite_path="rune.png", behaviour="magic") # a literal sprite, cool glow
```

`sprite_path` is either a **literal file path** (`"a/b.png"`) or a **theme
sprite-name** the active theme resolves to a file. `behaviour` is a **preset**
from the general registry in [`behaviours.py`](./behaviours.py) — it is
theme-independent (`behaviour="light"` shines the same in every pack) and **never
picks a sprite**. A behaviour only ever fills in general renderer primitives:

- `glow` (RGB) + `glow_radius` (tiles) + `glow_strength` (1.0 = a lamp)
- `flicker` (0…~0.3 — flame waver on the glow)
- `smoke` (a soft drift of smoke/steam)
- `floor` (draw in the ground layer, no shadow, agents stand centred on top)

Anything you set explicitly wins — `Renderable(behaviour="lamp", glow=(0,255,0))`
keeps the green light; the behaviour only supplies what you left unset.

## Preset behaviours

Pick the closest name; several names alias the same behaviour.

**Warm light**
| Behaviour (aliases) | Effect |
| --- | --- |
| `light` · `glow` · `lit` | soft warm light |
| `lamp` · `streetlamp` · `lantern` · `sconce` | wide warm light (lights a corner) |
| `candle` · `candlelight` | small warm light, gentle flicker |
| `window` · `lit_window` · `hearthlight` | warm interior spill |
| `doorway` · `door_glow` | hearth light spilling from a door |

**Fire & hearths** (glow + flicker, most also smoke)
| Behaviour (aliases) | Effect |
| --- | --- |
| `hearth` · `fireplace` | warm glow, flicker, smoke |
| `stove` · `oven` · `kiln` | ember glow + steam |
| `forge` · `furnace` | hot glow, strong flicker, smoke |
| `torch` · `brazier` | small flickering flame |
| `campfire` · `bonfire` · `fire` | big flickering glow + smoke |
| `ember` · `coals` · `lava` · `magma` | low hot-red glow |

**Cool / magical light**
| Behaviour (aliases) | Effect |
| --- | --- |
| `cool_light` · `moonlight` | cool wide light |
| `crystal` · `rune` · `magic` · `arcane` | cool glow, subtle flicker |
| `water_glow` · `fountain` · `shimmer` | cool water shimmer |
| `portal` · `vortex` | violet glow, strong flicker |

**Smoke / steam only** (no light)
| Behaviour (aliases) | Effect |
| --- | --- |
| `chimney` · `smoke` · `steam` · `vent` | a drift of smoke/steam |

**Walk-on ground terrain** (ground layer, no shadow, agents stand centred)
| Behaviour (aliases) | Effect |
| --- | --- |
| `floor` · `bridge` · `deck` · `boardwalk` · `rug` · `road` · `carpet` · `platform` | walk-on terrain |

## Write your own behaviour

A behaviour is just a named [`Render_Behaviour`](./behaviours.py) — a bundle of
the primitives above. Register it anywhere before the scene renders (e.g. at the
top of your example):

```python
from word_play.presets.renderers.behaviours import Render_Behaviour, register_behaviour

# a gently pulsing cyan waypoint marker
register_behaviour(
    Render_Behaviour(glow=(90, 220, 240), glow_radius=1.6, glow_strength=1.0, flicker=0.18),
    "waypoint", "beacon",          # one or more names/aliases
)

# then, on the entity:
Renderable(sprite_path="marker.png", behaviour="waypoint")
```

Guidelines:

- **Behaviour only.** If you find yourself wanting a behaviour to choose a
  sprite, reach for `sprite_path` instead — that is always the sprite knob.
- **Compose by bundling.** An oven that both glows and steams is one behaviour
  with `glow=…, smoke=True`; you don't stack multiple behaviours on one entity.
- **Tune glow to dusk/night.** `glow_strength` ~1.0 is a lamp; keep radii in the
  1–3 tile range so lights read without blowing out at 1× zoom.
- **Flicker sparingly.** `flicker` 0.1–0.25 reads as flame; higher looks strobey.
  Neighbouring fires auto-desync so a row of torches never pulses in lockstep.

Behaviour is theme-independent, so one you add works in every pack. Sprites stay
a theme concern (`theme.json` maps sprite-names → files); the two never mix.

## Dynamic behaviours (activatable)

A static `behaviour` is always on (a lamp always glows). A **dynamic behaviour**
is a named state an entity can *enter and leave* — fishing, sitting, chopping,
sleeping. They live in a separate registry,
[`dynamic_behaviours.py`](./dynamic_behaviours.py), and the sim drives one with a
single runtime field:

```python
Renderable(sprite_path="villager_gardener")          # normal
fisher.get_component(Renderable).action = "fishing"  # enter the state
fisher.get_component(Renderable).action = None       # leave it
```

While a dynamic behaviour is active the renderer:

- swaps to the **`_<pose>` sprite sibling** if one exists
  (`villager_gardener` → `villager_gardener_fishing`), auto-animated by its own
  `_2` frame — the same filename convention as `_2`/`_back`/`_glow`, so the
  behaviour never names a file itself (falls back to the base sprite if the pose
  art is missing);
- optionally **locks facing** (an angler faces the water);
- optionally shows a **looping effect** sprite a tile ahead of the entity (the
  cast splash on the lake), auto-animated via its `_2` frame.

A `Dynamic_Behaviour` bundles those: `pose`, `face`, `effect`,
`effect_forward` (tiles ahead), `effect_scale`. Register your own the same way as
static ones:

```python
from word_play.presets.renderers.dynamic_behaviours import (
    Dynamic_Behaviour, register_dynamic_behaviour)

register_dynamic_behaviour(
    Dynamic_Behaviour(pose="chopping", effect="wood_chips", effect_forward=0.6),
    "chopping",
)
# add villager_carpenter_chopping.png (+ _2) and wood_chips.png (+ _2), then:
worker.get_component(Renderable).action = "chopping"
```

The shipped `fishing` preset (`pose="fishing"`, `face="up"`,
`effect="catch_splash"`) shows the idea: the whole angler visual — rod pose,
facing the lake, cast splash — is one field the sim toggles, with no
sprite-swapping or effect-entity bookkeeping.

## The activity catalog (pose + effect contract)

These dynamic behaviours ship registered. Each row is the CONTRACT between the
renderer and the sprite packs: a pack that wants the full visual for an
activity ships `<character>_<pose>.png` (+ optional `_2`) siblings and binds
the effect sprite-name in its theme. Everything degrades gracefully — missing
pose art falls back to the base sprite, missing effect sprites are skipped —
so any behaviour can be activated against any sprite today.

| names | pose | face | effect (sprite-name) | forward |
|---|---|---|---|---|
| `fishing`, `angling` | `fishing` | up | `catch_splash` | 1.0 |
| `mining`, `digging` | `mining` | — | `ore_sparkle` | 0.7 |
| `cooking` | `cooking` | — | `steam` | 0.4 |
| `chopping`, `cutting` | `chopping` | — | `dust` | 0.6 |
| `cleaning`, `scrubbing` | `cleaning` | down | `dust` | 0.6 |
| `sweeping` | `sweeping` | — | `dust` | 0.5 |
| `planting`, `sowing` | `planting` | down | — | — |
| `harvesting`, `picking`, `foraging` | `harvesting` | — | `sparkle` | 0.6 |
| `watering` | `watering` | down | `water_drops` | 0.7 |
| `carrying`, `hauling` | `carrying` | — | — | — |
| `rowing`, `paddling` | `rowing` | — | `splash` (wake) | −0.6 |
| `working`, `operating`, `crafting` | `working` | — | — | — |
| `mixing` | `mixing` | — | `bubbles` | 0.4 |
| `repairing` | `repairing` | — | `spark` | 0.5 |
| `scanning` | `scanning` | — | `beam` | 0.8 |
| `attacking` | `attacking` | — | — | — |
| `celebrating`, `cheering` | `celebrating` | down | — | — |
| `sitting` | `sitting` | — | — | — |
| `sleeping`, `resting` | `sleeping` | — | — | — |
