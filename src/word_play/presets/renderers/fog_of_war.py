"""Fog of War - visibility calculation for grid-based environments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Entity


@dataclass(slots=True)
class Fog_Of_War:
    """
    Calculate visible tiles for an entity based on its position and sight radius.

    Usage:
        fog = Fog_Of_War(agent, sight_radius=5)
        visible = fog.visible_tiles(grid_width, grid_height)

    Or with custom distance metric:
        fog = Fog_Of_War(agent, sight_radius=3, distance_metric="manhattan")
    """

    entity: "Entity"
    sight_radius: int = 5
    distance_metric: str = "chebyshev"  # "chebyshev" or "manhattan"

    def visible_tiles(self, width: int, height: int) -> list[tuple[int, int]]:
        """Return list of visible (x, y) tile coordinates within the grid bounds."""
        pos = self.entity.position
        if pos is None:
            return []

        center_x = int(getattr(pos, "x", 0))
        center_y = int(getattr(pos, "y", 0))

        visible: list[tuple[int, int]] = []
        min_y = max(0, center_y - self.sight_radius)
        max_y = min(height - 1, center_y + self.sight_radius)
        min_x = max(0, center_x - self.sight_radius)
        max_x = min(width - 1, center_x + self.sight_radius)

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if self._is_visible(center_x, center_y, x, y):
                    visible.append((x, y))

        return visible

    def _is_visible(self, center_x: int, center_y: int, x: int, y: int) -> bool:
        """Check if a tile is within sight range using the configured distance metric."""
        if self.distance_metric == "manhattan":
            return abs(x - center_x) + abs(y - center_y) <= self.sight_radius
        # Default: chebyshev (max of dx, dy)
        return max(abs(x - center_x), abs(y - center_y)) <= self.sight_radius

    def is_tile_visible(self, x: int, y: int) -> bool:
        """Check if a specific tile is visible from the entity's current position."""
        pos = self.entity.position
        if pos is None:
            return False

        center_x = int(getattr(pos, "x", 0))
        center_y = int(getattr(pos, "y", 0))
        return self._is_visible(center_x, center_y, x, y)


def visible_tiles_for_entity(
    entity: "Entity",
    sight_radius: int,
    width: int,
    height: int,
    distance_metric: str = "chebyshev",
) -> list[tuple[int, int]]:
    """
    Convenience function to get visible tiles for an entity.

    Args:
        entity: The entity to calculate visibility from
        sight_radius: Maximum viewing distance
        width: Grid width
        height: Grid height
        distance_metric: "chebyshev" or "manhattan"

    Returns:
        List of (x, y) tuples representing visible tile coordinates
    """
    fog = Fog_Of_War(entity, sight_radius, distance_metric)
    return fog.visible_tiles(width, height)
