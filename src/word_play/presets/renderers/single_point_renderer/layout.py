"""SinglePointLayout — pick a preset, get a beautiful single-point chamber.

A single-point environment has every agent sharing one logical position.  This
layout fans the agents out into an arrangement (ring, two debating benches,
tiered senate, …) and dresses the chamber around them — marble floors, a red
carpet, a throne or podium, flanking statues and standards — so a static frame
reads like a summit, a senate, or a debate hall.

The single-point renderer draws *only agent entities*; every other element
(floor, carpet, focal piece, statues, flags) is emitted as background tiles by
this layout, so the agents are always the subject of the frame.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from word_play.presets.movement.single_point import Single_Point_Position
from word_play.presets.renderers.layout import Position_Layout_Adapter

if TYPE_CHECKING:
    from word_play.core import Environment, Render_Context


# ═══════════════════════════════════════════════════════════════════
# Sprite palette
# ═══════════════════════════════════════════════════════════════════

_MISC = "sprite_library/src/items/materials/misc"
_FLOORS = "sprite_library/src/world_tiles/indoors/floors"
_WALLS = "sprite_library/src/world_tiles/indoors/wall_sets"

FLOOR_MARBLE = f"{_FLOORS}/day_tile_floor_c.png"   # cool blue stone — civic / marble
FLOOR_WOOD = f"{_FLOORS}/wooden_floor.png"          # warm wood — chambers
FLOOR_STONE = f"{_FLOORS}/day_stone_floor_c.png"

CARPET = f"{_MISC}/red_carpet_c.png"
THRONE = f"{_MISC}/throne.png"
STATUE = f"{_MISC}/statue.png"
MOUNTED_STATUE = f"{_MISC}/mounted_statue.png"
PLANT = f"{_MISC}/potted_plants.png"
CANDLE = f"{_MISC}/wax_candle.png"
CHAIR_L = f"{_MISC}/wooden_chair_left.png"
CHAIR_R = f"{_MISC}/wooden_chair_right.png"
TABLE = "sprite_library/src/world_tiles/indoors/furniture/table_wood.png"
FLAG_RED = "sprite_library/src/items/special/flag_red.png"
FLAG_BLUE = "sprite_library/src/items/special/flag_blue.png"


@dataclass
class _State:
    cached_background: list[dict[str, Any]] | None = None
    offsets_by_entity: dict[Any, tuple[float, float]] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Preset configuration
#   offsets : how agents fan out
#   floor   : base floor sprite
#   wall    : wall set
#   carpet  : "disc" | "cross" | "v_runner" | "h_runner" | "two_aisles" | None
#   focal   : "throne_top" | "podium_top" | "long_table" | "twin_podiums" | None
#   flags   : "behind_focal" | "two_sides" | "ring" | None
#   statues : "flank_focal" | "corners" | "avenue" | None
#   plants  : corners on/off
# ═══════════════════════════════════════════════════════════════════

_PRESETS: dict[str, dict[str, Any]] = {
    "summit": {
        "offsets": "ring", "radius": 3.4, "floor": FLOOR_MARBLE, "wall": "castle_wall",
        "carpet": "disc", "focal": "round_table", "flags": "ring", "statues": "corners", "plants": True,
    },
    "ring": {
        "offsets": "ring", "radius": 3.2, "floor": FLOOR_WOOD, "wall": "lit_brick_wall",
        "carpet": "disc", "focal": "round_table", "flags": None, "statues": "corners", "plants": True,
    },
    "compass": {
        "offsets": "compass", "radius": 3.0, "floor": FLOOR_MARBLE, "wall": "lit_brick_wall",
        "carpet": "cross", "focal": "round_table", "flags": None, "statues": "corners", "plants": True,
    },
    "senate": {
        "offsets": "auditorium", "radius": 3.2, "floor": FLOOR_MARBLE, "wall": "castle_wall",
        "carpet": "v_runner", "focal": "throne_top", "flags": "behind_focal", "statues": "flank_focal", "plants": True,
    },
    "auditorium": {
        "offsets": "auditorium", "radius": 3.0, "floor": FLOOR_MARBLE, "wall": "dim_brick_wall",
        "carpet": "v_runner", "focal": "podium_top", "flags": "behind_focal", "statues": "flank_focal", "plants": False,
    },
    "throne": {
        "offsets": "audience", "radius": 3.0, "floor": FLOOR_MARBLE, "wall": "castle_wall",
        "carpet": "v_runner", "focal": "throne_top", "flags": "behind_focal", "statues": "avenue", "plants": True,
    },
    "debate": {
        "offsets": "debate", "radius": 3.0, "floor": FLOOR_MARBLE, "wall": "dim_fort_wall",
        "carpet": "v_runner", "focal": "twin_podiums", "flags": "two_sides", "statues": "flank_focal", "plants": True,
    },
    "boardroom": {
        "offsets": "boardroom", "radius": 2.8, "floor": FLOOR_WOOD, "wall": "lit_brick_wall",
        "carpet": "h_runner", "focal": "long_table", "flags": "behind_focal", "statues": "corners", "plants": True,
    },
    "horseshoe": {
        "offsets": "horseshoe", "radius": 2.9, "floor": FLOOR_WOOD, "wall": "lit_fort_wall",
        "carpet": "u_inside", "focal": "podium_bottom", "flags": "behind_focal", "statues": "corners", "plants": True,
    },
}
_DEFAULT_PRESET = "summit"


# ═══════════════════════════════════════════════════════════════════
# Offset generators — each returns exactly n (x, y) tuples
# ═══════════════════════════════════════════════════════════════════

def _ring_offsets(n: int, r: float) -> list[tuple[float, float]]:
    """Evenly spaced circle; y compressed 0.72× for a faux-isometric read."""
    if n == 1:
        return [(0.0, 0.0)]
    return [(r * math.cos(a), r * math.sin(a) * 0.72)
            for a in (-math.pi / 2 + 2 * math.pi * i / n for i in range(n))]


def _compass_offsets(n: int, r: float) -> list[tuple[float, float]]:
    if n == 1: return [(0.0, 0.0)]
    if n == 2: return [(-r, 0.0), (r, 0.0)]
    if n == 3: return [(0.0, -r * 0.72), (r * 0.87, r * 0.5), (-r * 0.87, r * 0.5)]
    if n == 4: return [(0.0, -r * 0.72), (r, 0.0), (0.0, r * 0.72), (-r, 0.0)]
    return _ring_offsets(n, r)


def _rows_offsets(n: int, r: float, *, top: float, cols_cap: int, row_gap: float, col_gap: float) -> list[tuple[float, float]]:
    """Centered rows that grow downward from ``top`` — used by senate/throne."""
    if n == 0:
        return []
    if n == 1:
        return [(0.0, top)]
    cols = max(2, min(cols_cap, int(round(math.sqrt(n) * 1.5))))
    offs: list[tuple[float, float]] = []
    remaining, row = n, 0
    while remaining > 0:
        row_cols = min(cols, remaining)
        y = top + row * row_gap
        for c in range(row_cols):
            x = -(row_cols - 1) * col_gap / 2 + c * col_gap
            offs.append((x, y))
        remaining -= row_cols
        row += 1
    # Center the block vertically so the crowd sits mid-chamber.
    mean_y = sum(y for _, y in offs) / len(offs)
    return [(x, y - mean_y) for x, y in offs]


def _auditorium_offsets(n: int, r: float) -> list[tuple[float, float]]:
    return _rows_offsets(n, r, top=-r * 0.2, cols_cap=8, row_gap=r * 0.62, col_gap=r * 0.5)


def _audience_offsets(n: int, r: float) -> list[tuple[float, float]]:
    # Tighter columns hugging the central carpet, leaving the top for the throne.
    return _rows_offsets(n, r, top=r * 0.1, cols_cap=6, row_gap=r * 0.6, col_gap=r * 0.55)


def _boardroom_offsets(n: int, r: float) -> list[tuple[float, float]]:
    """Seats along both long sides of a central table, then the two heads."""
    w, h = r * 1.5, r * 0.7
    per_side = max(1, (n - 2 + 1) // 2) if n > 2 else (n + 1) // 2

    def interp(i, count):
        return 0.0 if count <= 1 else (((i / (count - 1)) * 2 - 1) * w)

    offs: list[tuple[float, float]] = []
    remaining = n
    top_n = min(per_side, remaining)
    offs += [(interp(i, top_n), -h) for i in range(top_n)]; remaining -= top_n
    bot_n = min(per_side, remaining)
    offs += [(interp(i, bot_n), h) for i in range(bot_n)]; remaining -= bot_n
    for hx in (-w - r * 0.35, w + r * 0.35):
        if remaining > 0:
            offs.append((hx, 0.0)); remaining -= 1
    if remaining > 0:
        offs += _ring_offsets(remaining, r * 1.6)
    return offs


def _horseshoe_offsets(n: int, r: float) -> list[tuple[float, float]]:
    """U of seats opening toward the bottom (podium)."""
    w, h = r * 1.2, r * 0.85
    top_n = max(1, n - 2 * ((n) // 3))
    side_n = (n - top_n + 1) // 2
    side_n2 = n - top_n - side_n

    def interp(i, count):
        return 0.0 if count <= 1 else (((i / (count - 1)) * 2 - 1) * w)

    offs = [(interp(i, top_n), -h) for i in range(top_n)]
    for i in range(side_n):
        frac = (i + 1) / (side_n + 1)
        offs.append((-w, -h + frac * 1.7 * h))
    for i in range(side_n2):
        frac = (i + 1) / (side_n2 + 1)
        offs.append((w, -h + frac * 1.7 * h))
    return offs[:n] if len(offs) >= n else offs + _ring_offsets(n - len(offs), r * 1.6)


def _debate_offsets(n: int, r: float) -> list[tuple[float, float]]:
    """Two benches facing across a central aisle."""
    w, h = r * 0.95, r * 0.85
    left_n = (n + 1) // 2
    right_n = n - left_n

    def col(count, x):
        if count == 0: return []
        if count == 1: return [(x, 0.0)]
        return [(x, (((i / (count - 1)) * 2 - 1) * h)) for i in range(count)]

    return col(left_n, -w) + col(right_n, w)


_OFFSETS = {
    "ring": _ring_offsets, "compass": _compass_offsets,
    "auditorium": _auditorium_offsets, "audience": _audience_offsets,
    "boardroom": _boardroom_offsets, "horseshoe": _horseshoe_offsets,
    "debate": _debate_offsets,
}


# ═══════════════════════════════════════════════════════════════════
# Room construction
# ═══════════════════════════════════════════════════════════════════

def _room_half_extent(cfg: dict, n: int) -> tuple[int, int]:
    """Half-width / half-height of the chamber interior, sized to snugly fit
    the crowd: take the actual agent offset spread and add a walking margin."""
    fn = _OFFSETS.get(cfg["offsets"], _ring_offsets)
    offsets = fn(max(1, n), cfg["radius"])
    max_x = max((abs(ox) for ox, _ in offsets), default=1.0)
    max_y = max((abs(oy) for _, oy in offsets), default=1.0)
    # Margin leaves room for the carpet border, statues and a wall gap.
    hw = max(4, int(math.ceil(max_x)) + 3)
    hh = max(4, int(math.ceil(max_y)) + 3)
    return (hw, hh)


def _tile(x: int, y: int, sprite: str) -> dict[str, Any]:
    return {"x": x, "y": y, "kind": "floor", "sprite": sprite}


def _build_room(cfg: dict, n: int, bx: int, by: int) -> list[dict[str, Any]]:
    hw, hh = _room_half_extent(cfg, n)
    tiles: list[dict[str, Any]] = []

    # 1. Base floor.
    for y in range(-hh, hh + 1):
        for x in range(-hw, hw + 1):
            tiles.append(_tile(bx + x, by + y, cfg["floor"]))

    # 2. Carpet.
    carpet = cfg.get("carpet")
    cx0 = 0
    if carpet == "disc":
        rad = min(hw, hh) - 1
        for y in range(-hh, hh + 1):
            for x in range(-hw, hw + 1):
                if (x * x) / max(1, rad * rad) + (y * y) / max(1, (rad - 0) ** 2) <= 1.05:
                    tiles.append(_tile(bx + x, by + y, CARPET))
    elif carpet == "cross":
        for d in range(-hh + 1, hh):
            tiles.append(_tile(bx, by + d, CARPET))
        for d in range(-hw + 1, hw):
            tiles.append(_tile(bx + d, by, CARPET))
    elif carpet == "v_runner":
        for y in range(-hh + 1, hh):
            tiles.append(_tile(bx + cx0, by + y, CARPET))
            tiles.append(_tile(bx + cx0 - 1, by + y, CARPET))
    elif carpet == "h_runner":
        for x in range(-hw + 1, hw):
            tiles.append(_tile(bx + x, by, CARPET))
    elif carpet == "u_inside":
        for y in range(-hh + 1, 1):
            for x in range(-hw + 2, hw - 1):
                tiles.append(_tile(bx + x, by + y, CARPET))

    # 3. Focal piece(s).
    focal = cfg.get("focal")
    top_y = -hh + 1
    if focal == "round_table":
        tiles.append(_tile(bx, by, TABLE))
    elif focal == "long_table":
        span = max(1, hw - 2)
        for x in range(-span, span + 1):
            tiles.append(_tile(bx + x, by, TABLE))
    elif focal == "throne_top":
        tiles.append(_tile(bx, by + top_y, THRONE))
    elif focal == "podium_top":
        tiles.append(_tile(bx, by + top_y, TABLE))
    elif focal == "podium_bottom":
        tiles.append(_tile(bx, by + hh - 1, TABLE))
    elif focal == "twin_podiums":
        tiles.append(_tile(bx - 1, by + top_y, TABLE))
        tiles.append(_tile(bx + 1, by + top_y, TABLE))

    # 4. Flags.
    flags = cfg.get("flags")
    if flags == "behind_focal":
        tiles.append(_tile(bx - 2, by + top_y, FLAG_BLUE))
        tiles.append(_tile(bx + 2, by + top_y, FLAG_RED))
    elif flags == "two_sides":
        for y in (-hh + 1, hh - 1):
            tiles.append(_tile(bx - hw + 1, by + y, FLAG_BLUE))
            tiles.append(_tile(bx + hw - 1, by + y, FLAG_RED))
    elif flags == "ring":
        for i, (fx, fy) in enumerate([(0, -hh + 1), (hw - 1, 0), (0, hh - 1), (-hw + 1, 0)]):
            tiles.append(_tile(bx + fx, by + fy, FLAG_RED if i % 2 else FLAG_BLUE))

    # 5. Statues.
    statues = cfg.get("statues")
    corners = [(-hw + 1, -hh + 1), (hw - 1, -hh + 1), (-hw + 1, hh - 1), (hw - 1, hh - 1)]
    if statues == "corners":
        for sx, sy in corners:
            tiles.append(_tile(bx + sx, by + sy, STATUE))
    elif statues == "flank_focal":
        tiles.append(_tile(bx - 1, by + top_y, MOUNTED_STATUE))
        tiles.append(_tile(bx + 1, by + top_y, MOUNTED_STATUE))
    elif statues == "avenue":
        for y in range(top_y + 2, hh - 1, 3):
            tiles.append(_tile(bx - 2, by + y, STATUE))
            tiles.append(_tile(bx + 2, by + y, STATUE))

    # 6. Potted plants softening the corners.
    if cfg.get("plants"):
        for sx, sy in corners:
            if not any(t["x"] == bx + sx and t["y"] == by + sy and t["sprite"] == STATUE for t in tiles):
                tiles.append(_tile(bx + sx, by + sy, PLANT))

    # 7. Walls.
    wall_set = f"{_WALLS}/{cfg['wall']}"
    for y in range(-hh - 1, hh + 2):
        for x in range(-hw - 1, hw + 2):
            if y in (-hh - 1, hh + 1) or x in (-hw - 1, hw + 1):
                tiles.append({"x": bx + x, "y": by + y, "kind": "wall", "wall_set": wall_set})
    return tiles


# ═══════════════════════════════════════════════════════════════════
# Layout adapter
# ═══════════════════════════════════════════════════════════════════

class SinglePointLayout(Position_Layout_Adapter):
    """Arrange single-point agents into a dressed chamber.

    Presets::

        summit      Agents ringed around a round table on a red rug, standards
                    at the cardinal points, statues in the corners.  Marble.
        ring        Warm-wood circular chamber with a central table.
        compass     N/E/S/W placement on a carpet cross.  Best for ≤4.
        senate      Tiered rows facing a throne, carpet aisle, flanking statues
                    and standards.  Marble.
        auditorium  Tiered rows facing a podium.  Plainer senate.
        throne      Throne at the head, a carpet avenue lined with statues, the
                    crowd massed along it.
        debate      Two benches facing across a carpet aisle, blue vs red
                    standards, twin podiums, statues at the centre line.
        boardroom   Long table down the chamber, delegates either side, a
                    standard and statues framing the head.
        horseshoe   U of seats opening onto a podium.

    The renderer draws only agent entities; the chamber is background.
    """

    only_agents = True  # single-point renderer renders agent entities only

    def __init__(self, layout_mode: str = _DEFAULT_PRESET):
        cfg = _PRESETS.get(layout_mode, _PRESETS[_DEFAULT_PRESET])
        self.layout_mode = layout_mode if layout_mode in _PRESETS else _DEFAULT_PRESET
        self.cfg = cfg
        self.base_x = 0
        self.base_y = 0
        self.radius = cfg["radius"]
        self.DEFAULT_FLOOR = cfg["floor"]
        self.WALL_SET = f"{_WALLS}/{cfg['wall']}"
        self.groups: list[list[str]] = []

    # -- public tuning -------------------------------------------------
    def set_groups(self, *groups: list[str]) -> "SinglePointLayout":
        """Order agents by side/group (e.g. pro vs con for ``debate``)."""
        self.groups = [list(g) for g in groups]
        return self

    # -- single-point renders only agents ------------------------------
    def should_render(self, entity: Any) -> bool:
        return bool(getattr(entity, "is_agent", False))

    # -- internals -----------------------------------------------------
    def _state(self, ctx) -> _State:
        if ctx is None:
            raise ValueError("SinglePointLayout requires a Render_Context.")
        return ctx.value_for(self, _State)

    def _agents(self, env) -> list[Any]:
        ents = list(getattr(env.state, "entities", []))
        agents = [e for e in ents if getattr(e, "is_agent", False)]
        agents.sort(key=lambda e: e.name)
        if self.groups:
            order = {name: gi for gi, g in enumerate(self.groups) for name in g}
            agents.sort(key=lambda e: (order.get(e.name, len(self.groups)), e.name))
        return agents

    # -- Position_Layout_Adapter interface -----------------------------
    def prepare_env(self, env: "Environment", context: "Render_Context | None" = None) -> None:
        if env is None:
            return
        st = self._state(context)
        agents = self._agents(env)
        n = len(agents)
        st.offsets_by_entity.clear()
        st.cached_background = None
        if n == 0:
            return
        fn = _OFFSETS.get(self.cfg["offsets"], _ring_offsets)
        offsets = fn(n, self.radius)
        assert len(offsets) == n, f"{self.layout_mode}: {len(offsets)} offsets for {n} agents"
        for e, off in zip(agents, offsets):
            st.offsets_by_entity[e] = off

    def background(self, env, positioned_entities, context=None):
        st = self._state(context)
        if st.cached_background is not None:
            return st.cached_background
        if env is None:
            return []
        n = len(self._agents(env))
        if n == 0:
            st.cached_background = []
            return []
        st.cached_background = _build_room(self.cfg, n, self.base_x, self.base_y)
        return st.cached_background

    def screen_position(self, entity, env, context=None):
        pos = getattr(entity, "position", entity)
        if isinstance(pos, Single_Point_Position):
            ox, oy = self._state(context).offsets_by_entity.get(entity, (0.0, 0.0))
            return (self.base_x + ox, self.base_y + oy)
        x, y = getattr(pos, "x", None), getattr(pos, "y", None)
        if x is not None and y is not None:
            return (float(x), float(y))
        return (self.base_x, self.base_y)
