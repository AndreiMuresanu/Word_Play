from __future__ import annotations

from word_play.core.components import Component


class Renderable(Component):
    """Pygame sprite metadata for an entity."""

    def __init__(
        self,
        sprite_path: str,
        z_index: int = 0,
        visible: bool = True,
        overlay_sprite: str | None = None,
        overlay_mode: str = "badge",
        overlay_scale: float | None = None,
        wall_set: str | None = None,
    ):
        super().__init__()
        self.sprite_path = sprite_path
        self.wall_set = wall_set
        self.z_index = z_index
        self.visible = visible
        self.overlay_sprite = overlay_sprite
        self.overlay_mode = overlay_mode
        self.overlay_scale = overlay_scale
