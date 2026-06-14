from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from word_play.core import Environment

    from ..layout import Position_Layout_Adapter
    from .renderer import Pygame_Renderer


_PYGAME_RUNTIME_KEY = object()


@dataclass(slots=True)
class Pygame_Session_State:
    pygame_initialized: bool = False
    image_cache: dict[str, Any] = field(default_factory=dict)
    scaled_image_cache: dict[tuple[str, int, int], Any] = field(default_factory=dict)
    wall_set_cache: dict[str, dict[str, str]] = field(default_factory=dict)
    vignette_cache: dict[tuple[int, int], Any] = field(default_factory=dict)
    window_size: tuple[int, int] | None = None


@dataclass(slots=True)
class Pygame_View_State:
    selected_entity: Any | None = None
    camera_focus_entity: Any | None = None
    camera_focus_radius_tiles: int = 1
    last_drawn_entity_rects: dict[Any, pygame.Rect] = field(default_factory=dict)


@dataclass(slots=True)
class Pygame_Effect_State:
    last_health_values: dict[Any, float] = field(default_factory=dict)
    damage_flash_until: dict[Any, float] = field(default_factory=dict)
    camera_shake_until: float = 0.0
    camera_shake_strength: float = 0.0


@dataclass(slots=True)
class Pygame_Prompt_State:
    active: bool = False
    title: str = ""
    body: str = ""
    prompt: str = "> "
    input_text: str = ""
    history_blocks: list[str] = field(default_factory=list)
    scroll_lines: int = 0
    panel_rect: pygame.Rect | None = None


@dataclass(slots=True)
class Pygame_Runtime_State:
    session: Pygame_Session_State = field(default_factory=Pygame_Session_State)
    view: Pygame_View_State = field(default_factory=Pygame_View_State)
    effects: Pygame_Effect_State = field(default_factory=Pygame_Effect_State)
    prompt: Pygame_Prompt_State = field(default_factory=Pygame_Prompt_State)


def pygame_runtime(renderer: "Pygame_Renderer") -> Pygame_Runtime_State:
    return renderer.render_context.value_for(_PYGAME_RUNTIME_KEY, Pygame_Runtime_State)


def configure_renderer(
    renderer: "Pygame_Renderer",
    *,
    layout: "Position_Layout_Adapter",
    tile_size: int,
) -> None:
    """Initialize renderer configuration, caches, and transient state."""
    renderer.render_context.private[_PYGAME_RUNTIME_KEY] = Pygame_Runtime_State()
    runtime = pygame_runtime(renderer)
    renderer.layout = layout
    renderer.base_tile_size = tile_size
    renderer.display_safe_margin = 72
    apply_renderer_metrics(renderer, tile_size)
    renderer.focus_outline_color = (245, 214, 102)
    renderer.selection_outline_color = (128, 203, 255)
    renderer.selection_panel_accent = (128, 203, 255)
    runtime.session.window_size = None


def focused_radius(env: "Environment", renderer: "Pygame_Renderer") -> int:
    radius = getattr(env, "observation_radius", pygame_runtime(renderer).view.camera_focus_radius_tiles)
    render_state = getattr(env, "render_state", None)
    if render_state is not None:
        radius = render_state.frame.get("camera.focus_radius", radius)
    return max(0, int(radius))


def handle_entity_click(
    renderer: "Pygame_Renderer",
    env: "Environment",
    mouse_pos: tuple[int, int],
    *,
    button: int = 1,
) -> None:
    view = pygame_runtime(renderer).view
    hit_entity = None
    for entity, rect in reversed(list(view.last_drawn_entity_rects.items())):
        if rect.collidepoint(mouse_pos):
            hit_entity = entity
            break

    if hit_entity is not None:
        if button == 1:
            view.selected_entity = hit_entity
            return

        if button == 3:
            if view.camera_focus_entity is hit_entity:
                view.camera_focus_entity = None
                return

            view.camera_focus_entity = hit_entity
            view.camera_focus_radius_tiles = focused_radius(env, renderer)
            return

    if button == 1:
        view.selected_entity = None
    elif button == 3:
        view.camera_focus_entity = None


def apply_renderer_metrics(renderer: "Pygame_Renderer", tile_size: int) -> None:
    """Apply tile-size-derived layout metrics and rebuild dependent font state."""
    renderer.tile_size = tile_size
    renderer.hud_height = max(100, min(180, tile_size * 3 + 24))
    renderer.terminal_height = max(240, min(420, tile_size * 5 + 60))
    renderer.terminal_width = max(460, min(760, tile_size * 11 + 180))
    renderer.margin = max(12, tile_size // 2)
    renderer.viewport_pad_w = renderer.margin
    renderer.viewport_pad_e = renderer.margin
    renderer.viewport_pad_s = renderer.margin
    renderer.viewport_pad_n = max(renderer.margin, int(tile_size * 2.15))

    if pygame_runtime(renderer).session.pygame_initialized:
        renderer.font = pygame.font.SysFont(None, renderer.tile_size)
        renderer.small_font = pygame.font.SysFont(None, max(16, renderer.tile_size // 2))
        renderer.sidebar_font = pygame.font.SysFont(None, max(13, int(renderer.tile_size * 0.32)))
        renderer.hud_font = pygame.font.SysFont(None, max(20, renderer.tile_size // 2 + 6))
        renderer.speech_fonts = [
            pygame.font.SysFont(None, max(13, renderer.tile_size // 3)),
            pygame.font.SysFont(None, max(11, renderer.tile_size // 4)),
            pygame.font.SysFont(None, 10),
        ]


def desktop_size() -> tuple[int, int]:
    """Return the primary desktop size using display APIs meant for monitor geometry."""
    try:
        sizes = pygame.display.get_desktop_sizes()
        if sizes:
            width, height = sizes[0]
            if width > 0 and height > 0:
                return int(width), int(height)
    except Exception:
        pass

    info = pygame.display.Info()
    if info.current_w > 0 and info.current_h > 0:
        return int(info.current_w), int(info.current_h)

    return 1440, 900


def fitted_tile_size(
    renderer: "Pygame_Renderer",
    *,
    grid_width: int,
    grid_height: int,
    sidebar_width: int,
    hud_visible: bool,
) -> int:
    """Choose a tile size that fits the display while keeping small scenes legible."""
    screen_w, screen_h = desktop_size()
    max_width = max(640, screen_w - renderer.display_safe_margin)
    max_height = max(480, screen_h - renderer.display_safe_margin)
    min_width = max(420, screen_w // 2)
    min_height = max(320, screen_h // 2)
    base_tile = max(16, int(getattr(renderer, "base_tile_size", renderer.tile_size)))

    fitting_tiles: list[int] = []
    min_halfscreen_tile: int | None = None

    for tile_size in range(16, 257):
        margin = max(12, tile_size // 2)
        viewport_pad_n = max(margin, int(tile_size * 2.15))
        viewport_pad_s = margin
        viewport_pad_w = margin
        viewport_pad_e = margin
        hud_height = max(156, tile_size * 4) if hud_visible else 0
        terminal_height = max(240, min(420, tile_size * 5 + 60))
        terminal_width = max(460, min(760, tile_size * 11 + 180))
        scaled_sidebar = 0
        if sidebar_width > 0:
            scaled_sidebar = max(280, int(round(sidebar_width * (tile_size / max(1, base_tile)))))
        right_panel_width = max(terminal_width, scaled_sidebar)
        world_height = viewport_pad_n + viewport_pad_s + grid_height * tile_size
        content_height = max(world_height, terminal_height)
        width = viewport_pad_w + viewport_pad_e + grid_width * tile_size + right_panel_width
        height = content_height + hud_height
        if width <= max_width and height <= max_height:
            fitting_tiles.append(tile_size)
        if min_halfscreen_tile is None and (width >= min_width or height >= min_height):
            min_halfscreen_tile = tile_size

    if not fitting_tiles:
        return 16

    max_fit_tile = fitting_tiles[-1]
    if base_tile > max_fit_tile:
        return max_fit_tile
    if min_halfscreen_tile is not None and base_tile < min_halfscreen_tile:
        return min_halfscreen_tile
    if base_tile in fitting_tiles:
        return base_tile
    return max_fit_tile


def init_pygame_if_needed(renderer: "Pygame_Renderer") -> None:
    """Create the pygame window and fonts the first time rendering is used."""
    runtime = pygame_runtime(renderer)
    if runtime.session.pygame_initialized:
        return

    pygame.init()
    pygame.font.init()
    renderer.screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Environment Render")
    runtime.session.pygame_initialized = True
    apply_renderer_metrics(renderer, renderer.tile_size)


def ensure_screen_size(renderer: "Pygame_Renderer", width: int, height: int) -> None:
    """Resize the pygame window only when the target dimensions change."""
    runtime = pygame_runtime(renderer)
    desired_size = (width, height)
    if runtime.session.window_size == desired_size:
        return
    renderer.screen = pygame.display.set_mode(desired_size)
    runtime.session.window_size = desired_size


def scroll_prompt_lines(renderer: "Pygame_Renderer", delta_lines: int) -> None:
    prompt = pygame_runtime(renderer).prompt
    prompt.scroll_lines = max(0, prompt.scroll_lines + delta_lines)


def set_prompt_scroll_home(renderer: "Pygame_Renderer") -> None:
    pygame_runtime(renderer).prompt.scroll_lines = 0


def set_prompt_scroll_end(renderer: "Pygame_Renderer") -> None:
    pygame_runtime(renderer).prompt.scroll_lines = 10**9


def handle_prompt_panel_event(renderer: "Pygame_Renderer", event: pygame.event.Event) -> bool:
    prompt = pygame_runtime(renderer).prompt
    panel_rect = prompt.panel_rect
    if panel_rect is None:
        return False

    if event.type == pygame.MOUSEWHEEL:
        if panel_rect.collidepoint(pygame.mouse.get_pos()):
            scroll_prompt_lines(renderer, -event.y * 3)
            return True
        return False

    if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
        if panel_rect.collidepoint(event.pos):
            scroll_prompt_lines(renderer, 3 if event.button == 5 else -3)
            return True
        return False

    if event.type != pygame.KEYDOWN:
        return False

    if not prompt.active and not panel_rect.collidepoint(pygame.mouse.get_pos()):
        return False

    if event.key == pygame.K_PAGEUP:
        scroll_prompt_lines(renderer, -12)
        return True
    if event.key == pygame.K_PAGEDOWN:
        scroll_prompt_lines(renderer, 12)
        return True
    if event.key == pygame.K_HOME:
        set_prompt_scroll_home(renderer)
        return True
    if event.key == pygame.K_END:
        set_prompt_scroll_end(renderer)
        return True
    if event.key == pygame.K_UP:
        scroll_prompt_lines(renderer, -1)
        return True
    if event.key == pygame.K_DOWN:
        scroll_prompt_lines(renderer, 1)
        return True

    return False
