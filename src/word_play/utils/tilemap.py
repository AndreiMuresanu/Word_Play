from __future__ import annotations

from word_play.core import Entity


def ascii_to_tilemap_array(ascii_tilemap: str, tileset: dict[str, dict]) -> list[list[str]]:
    pass


# TODO: ANDREI: create fuction which returns a list of entites given a 2D array. This func would be used so that we can
#       just define a tilemap instead of a giant list of wall entities. The function signature should be something like:
#       tilemap_to_entites(tilemap: list[list[str]], tileset: dict[str, dict]) -> list[Entity]. The values of the
#       tileset are all of the args required to init the entity with the exception of the position arg which is added
#       from the tilemap. I think this is better than deepcopying an entity with a random position since we don't know
#       what logic needs to exec in the entity's init
def tilemap_to_entities(tilemap: list[list[str]] | str, tileset: dict[str, dict]) -> list[Entity]:
    if isinstance(tilemap, str):
        tilemap = ascii_to_tilemap_array(tilemap)
    pass
