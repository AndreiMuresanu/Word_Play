from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame

from ..themes import MISSING_ROLE_PREFIX, NEUTRAL_FLOOR_SPRITE, _project_root, is_sprite_name, resolve_sprite
from .beautify import build_soft_shadow, harmonize_surface
from .runtime import pygame_runtime
from .wall_geometry import adjacent_wall_variant_name, wall_connections

if TYPE_CHECKING:
    from .renderer import Pygame_Renderer


def candidate_asset_paths(asset_name: str) -> list[Path]:
    """Return the filesystem locations to try for a sprite or asset name."""
    project_root = _project_root()
    return [
        Path(asset_name),
        project_root / asset_name,
        project_root / "sprite_library" / asset_name,
    ]




def neutral_floor_surface() -> pygame.Surface:
    """A quiet procedural ground tile for environments with no theme or floor art.

    Unlike the magenta missing-role checker, this is a legitimate default (an
    intentional neutral stage, not an authoring error), so it stays subtle: a
    barely-there two-tone check with a few deterministic speckles.
    """
    size, cell = 16, 8
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    for cy in range(0, size, cell):
        for cx in range(0, size, cell):
            color = (74, 78, 84) if ((cx + cy) // cell) % 2 == 0 else (70, 74, 80)
            surface.fill(color, pygame.Rect(cx, cy, cell, cell))
    for i, (sx, sy) in enumerate(((3, 5), (11, 2), (7, 12), (13, 10))):
        speckle = (66, 70, 76) if i % 2 else (80, 84, 90)
        surface.fill(speckle, pygame.Rect(sx, sy, 1, 1))
    return surface


def missing_role_surface(role: str) -> pygame.Surface:
    """The magenta/black checkerboard drawn for roles a theme doesn't bind.

    Loud on purpose (the classic missing-texture convention): the sim keeps
    running and the author can see exactly which tile is unbound.
    """
    size, cell = 16, 4
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    for cy in range(0, size, cell):
        for cx in range(0, size, cell):
            color = (222, 44, 222) if ((cx + cy) // cell) % 2 == 0 else (16, 8, 16)
            surface.fill(color, pygame.Rect(cx, cy, cell, cell))
    return surface


def get_or_load_image(renderer: "Pygame_Renderer", sprite_name: str) -> Any | None:
    """Load a sprite once and reuse it from the renderer cache."""
    session = pygame_runtime(renderer).session
    if sprite_name in session.image_cache:
        return session.image_cache[sprite_name]

    if is_sprite_name(sprite_name):
        # bare name ("tree"): theme, then library index, then placeholder
        surface = get_or_load_image(renderer, resolve_sprite(renderer.theme, sprite_name))
        session.image_cache[sprite_name] = surface
        return surface

    if sprite_name.startswith(MISSING_ROLE_PREFIX):
        surface = missing_role_surface(sprite_name.removeprefix(MISSING_ROLE_PREFIX))
        session.image_cache[sprite_name] = surface
        return surface

    if sprite_name == NEUTRAL_FLOOR_SPRITE:
        surface = neutral_floor_surface()
        session.image_cache[sprite_name] = surface
        return surface

    for path in candidate_asset_paths(sprite_name):
        if path.exists() and path.is_file():
            surface = pygame.image.load(str(path)).convert_alpha()
            surface = harmonize_surface(surface, sprite_name, renderer.beautify)
            session.image_cache[sprite_name] = surface
            return surface

    session.image_cache[sprite_name] = None
    return None


def get_scaled_image(renderer: "Pygame_Renderer", sprite_name: str, width: int, height: int) -> Any | None:
    """Load and cache a sprite scaled to the requested dimensions."""
    session = pygame_runtime(renderer).session
    cache_key = (sprite_name, width, height)
    if cache_key in session.scaled_image_cache:
        return session.scaled_image_cache[cache_key]

    image = get_or_load_image(renderer, sprite_name)
    if image is None:
        session.scaled_image_cache[cache_key] = None
        return None

    scaled = pygame.transform.scale(image, (width, height))
    session.scaled_image_cache[cache_key] = scaled
    return scaled


def get_soft_shadow(renderer: "Pygame_Renderer", sprite_name: str, size: int) -> Any | None:
    """Return a cached, silhouette-derived contact shadow for a sprite at ``size``."""
    def build() -> Any | None:
        scaled = get_scaled_image(renderer, sprite_name, size, size)
        return None if scaled is None else build_soft_shadow(scaled, renderer.beautify)

    cache = pygame_runtime(renderer).session.scaled_image_cache
    return cache.get_or_build(("__shadow__", sprite_name, size), build)


def resolve_wall_sprite(renderer: "Pygame_Renderer", wall_set: str, neighbors: dict[str, bool]) -> str | None:
    """Choose the best wall sprite variant for a tile based on neighbors.

    Memoized per (set, cardinal connections): the variant choice depends only
    on which of the four cardinal neighbors are walls, so the filesystem probe
    and scoring scan run at most once per distinct pattern per set.
    """
    session = pygame_runtime(renderer).session
    connections = wall_connections(neighbors)
    variant_key = (wall_set, connections)
    if variant_key in session.wall_variant_cache:
        return session.wall_variant_cache[variant_key]

    result = _resolve_wall_sprite_uncached(renderer, wall_set, neighbors, connections)
    session.wall_variant_cache[variant_key] = result
    return result


def _resolve_wall_sprite_uncached(
    renderer: "Pygame_Renderer",
    wall_set: str,
    neighbors: dict[str, bool],
    connections: tuple[str, ...],
) -> str | None:
    session = pygame_runtime(renderer).session
    wall_root = session.wall_root_cache.get(wall_set)
    if wall_root is None:
        wall_root = next(
            (path for path in candidate_asset_paths(wall_set) if path.exists() and path.is_dir()),
            None,
        )
        if wall_root is None:
            # missing wall art degrades to the caller's placeholder, not a crash
            return None
        session.wall_root_cache[wall_set] = wall_root

    available = session.wall_set_cache.get(wall_set)
    if available is None:
        available = {
            path.stem.removeprefix(f"{wall_root.name}_"): path.name
            for path in wall_root.glob("*.png")
            if path.is_file()
        }
        session.wall_set_cache[wall_set] = available

    target_variant = adjacent_wall_variant_name(neighbors)
    if target_variant in available:
        return f"{wall_set}/{available[target_variant]}"

    target_connections = set(connections)
    if len(target_connections) == 1:
        axis_fallback = "up_down" if next(iter(target_connections)) in {"up", "down"} else "left_right"
        if axis_fallback in available:
            return f"{wall_set}/{available[axis_fallback]}"

    def variant_connections(name: str) -> set[str]:
        if name in {"flat", "center"}:
            return set()
        return {part for part in name.split("_") if part in {"left", "right", "up", "down"}}

    best_name: str | None = None
    best_score: tuple[int, int, int] | None = None
    for name in available:
        if name == "center":
            continue
        candidate_connections = variant_connections(name)
        overlap = len(candidate_connections & target_connections)
        extra = len(candidate_connections - target_connections)
        missing = len(target_connections - candidate_connections)
        score = (overlap, -missing, -extra)
        if best_score is None or score > best_score:
            best_score = score
            best_name = name

    if best_name is not None and (best_score is not None and best_score[0] > 0 or not target_connections):
        return f"{wall_set}/{available[best_name]}"
    if "flat" in available:
        return f"{wall_set}/{available['flat']}"
    if "center" in available:
        return f"{wall_set}/{available['center']}"
    return None
