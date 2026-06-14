from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame

from .runtime import pygame_runtime
from .wall_geometry import adjacent_wall_variant_name, wall_connections

if TYPE_CHECKING:
    from .renderer import Pygame_Renderer


def candidate_asset_paths(asset_name: str) -> list[Path]:
    """Return the filesystem locations to try for a sprite or asset name."""
    project_root = Path(__file__).resolve().parents[4]
    return [
        Path(asset_name),
        project_root / asset_name,
        project_root / "sprite_library" / asset_name,
    ]


def get_or_load_image(renderer: "Pygame_Renderer", sprite_name: str) -> Any | None:
    """Load a sprite once and reuse it from the renderer cache."""
    session = pygame_runtime(renderer).session
    if sprite_name in session.image_cache:
        return session.image_cache[sprite_name]

    for path in candidate_asset_paths(sprite_name):
        if path.exists() and path.is_file():
            surface = pygame.image.load(str(path)).convert_alpha()
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


def resolve_wall_sprite(renderer: "Pygame_Renderer", wall_set: str, neighbors: dict[str, bool]) -> str | None:
    """Choose the best wall sprite variant for a tile based on neighbors."""
    session = pygame_runtime(renderer).session
    candidate_roots = candidate_asset_paths(wall_set)
    wall_root = next((path for path in candidate_roots if path.exists() and path.is_dir()), None)
    if wall_root is None:
        raise FileNotFoundError(f"Wall set folder could not be resolved: '{wall_set}'.")

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

    target_connections = set(wall_connections(neighbors))
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
