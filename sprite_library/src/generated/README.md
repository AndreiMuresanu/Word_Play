# Sprite packs

Cohesive 16x16 pixel-art packs: one palette, one light direction (top-left),
one outline style per pack. Each pack is a folder of PNGs plus a `theme.json`,
and the renderer loads it by folder name:

```python
from word_play.presets.renderers import Grid_Layout_Adapter, Pygame_Renderer, Renderable

renderer = Pygame_Renderer(Grid_Layout_Adapter(), theme="rustic_town")

Renderable(sprite_path="tree")          # the pack's tree
Renderable(sprite_path="wall")          # wall roles auto-tile
Renderable(sprite_path="lamp")          # glows at dusk/night (role_glow)
```

`available_themes()` lists every pack. Renderer-side details (behaviours,
moods, chrome) live in `src/word_play/presets/renderers/README.md` and
`BEHAVIOURS.md`.

## Packs

`worlds/` — general-purpose settings:

| Pack | Extends | Chrome | Contents |
|---|---|---|---|
| `interactive_city` | — | rustic | Streets, plaza, shops, villagers. |
| `lakeside_commons` | `interactive_city` | rustic | Lake, shore, dock, rowboat, lodge, angler poses. |
| `rustic_town` | `interactive_city` | rustic | Cottages and farms: professions, animals, kitchens, a full larder. |
| `autumn_town` | `rustic_town` | rustic | Fall foliage, harvest-stage crops. |
| `winter_town` | `rustic_town` | rustic | Snow cover, frosted crops. |
| `wildlands` | — | rustic | Foragers/anglers, wildlife, ore and mushrooms, river/cliff/palisade walls. |
| `river_cleanup` | `wildlands` | rustic | Debris piles, nets, signage. |
| `starfall_station` | — | slate | Space station: crew, robots, reactor/consoles, hull/cleanroom walls. |
| `chemistry_lab` | `starfall_station` | slate | Beakers, fume hood, lab gear. |
| `factory_floor` | `starfall_station` | slate | Assembly line: parts, pipes, tanks. |

`benchmarks/` — small per-benchmark packs (`mining_camp`, `orchard_commons`,
and sprite-only folders for other benchmark families).

## `theme.json`

| Field | Meaning |
|---|---|
| `name` | pack name |
| `extends` | optional base pack; unset roles/walls are inherited, glow/smoke/precedence merge (child wins) |
| `root` | optional folder the `roles` filenames live in (defaults to the pack folder) |
| `roles` | sprite-name → filename |
| `wall_roles` | sprite-name → wall-set subfolder (the auto-tiling variants, one ending `_center`) |
| `role_glow` | sprite-name → `[[r, g, b], radius_tiles, strength]` — lights at dusk/night |
| `role_smoke` | sprite-names that send up drifting smoke |
| `ground_precedence` | ground sprite-name → rank; higher ranks fringe over lower neighbours |
| `chrome` | UI style: `rustic`, `slate`, or `minimal` |

Names a pack doesn't bind fall back to the library-wide sprite index, then to a
magenta placeholder (with a one-time warning) — missing art never crashes a sim.

## File-name conventions (automatic, no API)

| Sibling file | Effect |
|---|---|
| `foo_2.png` | 2-frame animation (entities staggered, ground tiles in a checker) |
| `foo_back.png` | rear view while the entity walks away; walking left mirrors the sprite |
| `foo_<pose>.png` | pose swapped in while `renderable.action` is that dynamic behaviour (e.g. `_fishing`) |
| `foo_glow.png` | emissive pixels (windows, lamp heads) composited after dark |
| `foo_b.png`, `foo_c.png` | ground variants mixed in by tile position |

Letter suffixes are variants; `_2` is reserved for animation frames.

License: original procedural output of this repository — no external art.
