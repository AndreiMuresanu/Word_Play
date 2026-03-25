from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

if TYPE_CHECKING:
    from .renderer import PygameRenderer


def candidate_asset_paths(asset_name: str) -> list[Path]:
    project_root = Path(__file__).resolve().parents[4]
    return [
        Path(asset_name),
        project_root / asset_name,
        project_root / "sprite_library" / asset_name,
    ]


def get_or_load_image(renderer: "PygameRenderer", sprite_name: str) -> Any | None:
    if sprite_name in renderer._image_cache:
        return renderer._image_cache[sprite_name]

    for path in candidate_asset_paths(sprite_name):
        if path.exists() and path.is_file():
            surface = pygame.image.load(str(path)).convert_alpha()
            renderer._image_cache[sprite_name] = surface
            return surface

    renderer._image_cache[sprite_name] = None
    return None


def get_scaled_image(renderer: "PygameRenderer", sprite_name: str, width: int, height: int) -> Any | None:
    cache_key = (sprite_name, width, height)
    if cache_key in renderer._scaled_image_cache:
        return renderer._scaled_image_cache[cache_key]

    image = get_or_load_image(renderer, sprite_name)
    if image is None:
        renderer._scaled_image_cache[cache_key] = None
        return None

    scaled = pygame.transform.scale(image, (width, height))
    renderer._scaled_image_cache[cache_key] = scaled
    return scaled


def resolve_wall_sprite(renderer: "PygameRenderer", wall_set: str, neighbors: dict[str, bool]) -> str | None:
    from .wall_geometry import adjacent_wall_variant_name, wall_connections

    candidate_roots = candidate_asset_paths(wall_set)
    wall_root = next((path for path in candidate_roots if path.exists() and path.is_dir()), None)
    if wall_root is None:
        raise FileNotFoundError(f"Wall set folder could not be resolved: '{wall_set}'.")

    available = renderer._wall_set_cache.get(wall_set)
    if available is None:
        available = {
            path.stem.removeprefix(f"{wall_root.name}_"): path.name
            for path in wall_root.glob("*.png")
            if path.is_file()
        }
        renderer._wall_set_cache[wall_set] = available

    target_variant = adjacent_wall_variant_name(neighbors)
    if target_variant in available:
        return f"{wall_set}/{available[target_variant]}"

    connections = wall_connections(neighbors)
    if len(connections) == 1:
        axis_fallback = "up_down" if connections[0] in {"up", "down"} else "left_right"
        if axis_fallback in available:
            return f"{wall_set}/{available[axis_fallback]}"

    if target_variant == "flat" and "flat" in available:
        return f"{wall_set}/{available['flat']}"
    if "center" in available:
        return f"{wall_set}/{available['center']}"
    return None
