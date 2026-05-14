from __future__ import annotations

import copy
import textwrap

from word_play.core import Entity
from word_play.presets.movement.simple_2d_grid import Position_2D

Tile = str
TileStack = list[Tile]
TileCell = Tile | TileStack
TileGrid = list[list[TileCell]]


def ascii_to_tilemap_array(
    ascii_tilemap: str,
    empty_tile_symbol: str = ".",
) -> list[list[str]]:
    """Parse a multi-line ASCII tilemap into a rectangular 2D array.

    String tilemaps are dedented and stripped of leading/trailing blank lines so
    triple-quoted literals can be indented naturally in source code.

    Args:
        ascii_tilemap: Multi-line tilemap string.
        empty_tile_symbol: Single-character symbol used to represent empty tiles
            and to pad shorter rows so the result is rectangular.

    Returns:
        A rectangular 2D array of single-character strings.
    """
    if len(empty_tile_symbol) != 1:
        raise ValueError("empty_tile_symbol must be a single character")

    lines = textwrap.dedent(ascii_tilemap).splitlines()
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    lines = ["".join(tile for tile in line if not tile.isspace()) for line in lines]

    max_width = max((len(line) for line in lines), default=0)
    return [list(line.ljust(max_width, empty_tile_symbol)) for line in lines]


def find_tile_positions(
    tilemap: list[list[str]] | str,
    tiles: str | set[str],
    bottom_left_position: tuple[int, int] = (0, 0),
    empty_tile_symbol: str = ".",
) -> list[tuple[int, int]]:
    """Return world-space positions of tiles matching ``tiles``.

    Args:
        tilemap: Either a 2D tile array or a multi-line ASCII string.
        tiles: One or more tile symbols to search for.
        bottom_left_position: World-space ``(x, y)`` position of the tilemap's
            bottom-left cell.
        empty_tile_symbol: Empty-tile symbol used when parsing string tilemaps.
    """
    tile_set = set(tiles)
    if isinstance(tilemap, str):
        tilemap = ascii_to_tilemap_array(
            tilemap,
            empty_tile_symbol=empty_tile_symbol,
        )

    bottom_left_x, bottom_left_y = bottom_left_position
    tilemap_height = len(tilemap)
    return [
        (bottom_left_x + x, bottom_left_y + (tilemap_height - 1 - y))
        for y, row in enumerate(tilemap)
        for x, tile in enumerate(row)
        if tile in tile_set
    ]


def _normalize_cell_tiles(cell: TileCell, *, empty_tile_symbol: str) -> list[Tile]:
    if isinstance(cell, str):
        if len(cell) != 1:
            raise ValueError(f"Each tile must be a single-character string, got {cell!r}")
        return [] if cell == empty_tile_symbol else [cell]

    return [tile for tile in cell if tile != empty_tile_symbol]


def tilemap_to_entities(
    tilemap: TileGrid | str,
    tileset: dict[str, dict],
    bottom_left_position: tuple[int, int] = (0, 0),
    empty_tile_symbol: str = ".",
) -> list[Entity]:
    """Convert a tilemap into ``Entity`` objects using a tileset mapping.

    Args:
        tilemap: Either:
            1. A multi-line ASCII string.
            2. A 2D array of tile cells, where each cell is either a single
               tile symbol like ``"W"`` or a list of tile symbols like
               ``["I", "f"]`` for multiple entities on the same tile.
            String tilemaps are dedented and, by default, whitespace is treated
            as formatting rather than map data.
        tileset: Mapping from tile symbols to dictionaries of keyword
            arguments used to instantiate ``Entity`` objects. Each matching
            tile is converted with ``Entity(**kwargs)`` after overwriting the
            ``position`` field with the tile's computed world-space position.
            Empty tiles are skipped. Any other symbol must appear in
            ``tileset`` or a ``ValueError`` is raised.
        bottom_left_position: World-space ``(x, y)`` position assigned to the
            tilemap's bottom-left cell.
        empty_tile_symbol: Explicit symbol representing an empty tile.

    Returns:
        A list of entities for all non-empty tiles in the tilemap.

    Raises:
        ValueError: If a non-empty tile symbol is encountered that is not
            present in ``tileset``.

    Example:

        tileset = {
            "W": {"name": "Wall", "tags": ["wall"], "components": [Collidable()]},
            "P": {"name": "Spawn", "tags": ["spawn"]},
            "s": {"name": "Strawberry", "tags": ["item", "food"]},
        }
        tilemap = \"\"\"
        WWWWW
        WP.sW
        WWWWW
        \"\"\"
        entities = tilemap_to_entities(tilemap, tileset, bottom_left_position=(10, 5))
    """
    if isinstance(tilemap, str):
        tilemap = ascii_to_tilemap_array(
            tilemap,
            empty_tile_symbol=empty_tile_symbol,
        )

    bottom_left_x, bottom_left_y = bottom_left_position
    tilemap_height = len(tilemap)
    entities: list[Entity] = []
    for y, row in enumerate(tilemap):
        for x, cell in enumerate(row):
            world_x = bottom_left_x + x
            world_y = bottom_left_y + (tilemap_height - 1 - y)
            for tile in _normalize_cell_tiles(cell, empty_tile_symbol=empty_tile_symbol):
                if tile not in tileset:
                    raise ValueError(
                        f"Unexpected tile {tile!r} at tilemap position ({x}, {y}) "
                        f"with world position ({world_x}, {world_y})"
                    )
                kwargs = copy.deepcopy(tileset[tile])
                kwargs["position"] = Position_2D(world_x, world_y)
                entities.append(Entity(**kwargs))

    return entities
