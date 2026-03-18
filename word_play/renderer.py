from __future__ import annotations
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from word_play.environment import Component, Position

if TYPE_CHECKING:
    from word_play.environment import Environment


class Renderable(Component):
    def __init__(
        self,
        sprite: str | None = None,
        glyph: str = "?",
        color: tuple[int, int, int] = (255, 255, 255),
        z_index: int = 0,
        visible: bool = True,
    ):
        super().__init__()
        self.sprite = sprite
        self.glyph = glyph
        self.color = color
        self.z_index = z_index
        self.visible = visible


class Renderer(ABC):
    @abstractmethod
    def render(self, env: "Environment") -> Any:
        """Draw the given environment and return any renderer-specific output."""
        pass


class PositionLayoutAdapter(ABC):
    @abstractmethod
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert an environment position into screen/grid coordinates."""
        pass

    def background(self, env: "Environment") -> list:
        """Return optional background draw data for the environment."""
        return []


class TextRenderer(Renderer):
    def render(self, env: "Environment") -> str:
        """Render the environment as a simple text listing of entities."""
        lines = [env.description, "-" * 40]
        for entity in env.state.entities:
            rend = entity.get_component(Renderable)
            glyph = rend.glyph if rend else "?"
            lines.append(f"{glyph} {entity.name} @ {entity.position}")
        return "\n".join(lines)


class GridLayoutAdapter(PositionLayoutAdapter):
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Map a grid position directly to a grid-aligned screen position."""
        # Assumes position has x and y attributes
        return float(position.x), float(position.y)


class PygameRenderer(Renderer):
    def __init__(self, layout: PositionLayoutAdapter, tile_size: int = 32):
        """Store layout/render settings for later pygame drawing."""
        self.layout = layout
        self.tile_size = tile_size
        self._pygame_initialized = False

    def _init_pygame(self):
        """Initialize pygame, the window, and the default font once."""
        if not self._pygame_initialized:
            try:
                import pygame
            except ImportError:
                raise ImportError("pygame is required for PygameRenderer. Run `pip install pygame`")
            pygame.init()
            # Default window size, can be adjusted or passed in
            self.screen = pygame.display.set_mode((800, 600))
            pygame.display.set_caption("Environment Render")
            self.font = pygame.font.SysFont(None, self.tile_size)
            self._pygame_initialized = True

    def _get_or_load_image(self, sprite_name: str) -> Any | None:
        """Optionally resolve a logical sprite name to a pygame surface."""
        return None

    def _draw_overlay_item(self, item_name: str, px: int, py: int) -> None:
        """Draw a small overlay icon or fallback label on top of a tile."""
        import pygame

        item_image = self._get_or_load_image(item_name)
        if item_image is not None:
            overlay_size = max(18, self.tile_size // 2)
            item_image = pygame.transform.scale(item_image, (overlay_size, overlay_size))
            self.screen.blit(item_image, (px + self.tile_size - overlay_size, py))
            return

        fallback_font = getattr(self, "small_font", self.font)
        label = fallback_font.render(item_name[:2].upper(), True, (255, 240, 120))
        self.screen.blit(label, (px + self.tile_size - 18, py + 2))

    def render(self, env: "Environment") -> None:
        """Draw visible entities as colored tiles with glyph fallbacks."""
        import pygame
        self._init_pygame()

        self.screen.fill((0, 0, 0))  # Clear screen

        # Optionally draw background if layout adapter provides one
        # self.layout.background(env)
        
        renderables = []
        for entity in env.state.entities:
            renderable = entity.get_component(Renderable)
            if renderable and renderable.visible:
                renderables.append((renderable.z_index, entity, renderable))

        renderables.sort(key=lambda x: x[0])

        for _, entity, renderable in renderables:
            try:
                x, y = self.layout.screen_position(entity.position)
            except AttributeError:
                # If position doesn't have x,y and adapter fails, skip rendering this entity gracefully
                continue
                
            px = x * self.tile_size
            py = y * self.tile_size
            
            # Simple fallback rendering: draw a coloured rect and glyph if no sprite
            color = renderable.color
            rect = pygame.Rect(px, py, self.tile_size, self.tile_size)
            pygame.draw.rect(self.screen, color, rect)
            
            # Draw glyph label
            if renderable.glyph:
                # Choose black or white text depending on background darkness
                text_color = (0, 0, 0) if sum(color) > 382 else (255, 255, 255)
                text_surface = self.font.render(renderable.glyph, True, text_color)
                # Center text in tile
                text_rect = text_surface.get_rect(center=rect.center)
                self.screen.blit(text_surface, text_rect)

        pygame.display.flip()

        # Simple event pump to keep window responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
