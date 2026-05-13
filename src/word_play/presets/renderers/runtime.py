from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .renderer import Pygame_Renderer, Position_Layout_Adapter


def configure_renderer(
    renderer: "Pygame_Renderer",
    *,
    layout: "Position_Layout_Adapter",
    tile_size: int,
    draw_grid_overlay: bool = False,
) -> None:
    """Initialize renderer configuration, caches, and transient state."""
    renderer.layout = layout
    renderer.base_tile_size = tile_size
    renderer.display_fit_tile_size = tile_size
    renderer.display_safe_margin = 72
    apply_renderer_metrics(renderer, tile_size)
    renderer.default_draw_grid_overlay = draw_grid_overlay
    renderer.last_record_path = None
    renderer._pygame_initialized = False
    renderer._image_cache = {}
    renderer._scaled_image_cache = {}
    renderer._wall_set_cache = {}
    renderer._window_size = None
    renderer._last_health_values = {}
    renderer._damage_flash_until = {}
    renderer.camera_focus_entity_name = None
    renderer.camera_focus_radius_tiles = 6
    renderer.camera_smoothing = 0.24
    renderer.camera_center = None
    renderer.camera_shake_until = 0.0
    renderer.camera_shake_strength = 0.0
    renderer._last_drawn_entity_rects = {}
    renderer._entity_last_positions = {}
    renderer._sprite_particle_effects = {}
    renderer.pixel_art_mode = True
    renderer.focus_outline_color = (245, 214, 102)
    renderer.selection_outline_color = (128, 203, 255)
    renderer.selection_panel_accent = (128, 203, 255)
    renderer._vignette_cache = {}
    renderer.selected_entity_name = None


def apply_renderer_metrics(renderer: "Pygame_Renderer", tile_size: int) -> None:
    """Apply tile-size-derived layout metrics and rebuild dependent font state."""
    renderer.tile_size = tile_size
    renderer.hud_height = max(100, min(180, tile_size * 3 + 24))
    renderer.margin = max(12, tile_size // 2)
    renderer.viewport_pad_w = renderer.margin
    renderer.viewport_pad_e = renderer.margin
    renderer.viewport_pad_s = renderer.margin
    renderer.viewport_pad_n = max(renderer.margin, int(tile_size * 2.15))

    if getattr(renderer, "_pygame_initialized", False):
        renderer.font = pygame.font.SysFont(None, renderer.tile_size)
        renderer.small_font = pygame.font.SysFont(None, max(16, renderer.tile_size // 2))
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
        scaled_sidebar = 0
        if sidebar_width > 0:
            scaled_sidebar = max(280, int(round(sidebar_width * (tile_size / max(1, base_tile)))))
        width = viewport_pad_w + viewport_pad_e + grid_width * tile_size + scaled_sidebar
        height = viewport_pad_n + viewport_pad_s + grid_height * tile_size + hud_height
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
    if renderer._pygame_initialized:
        return

    pygame.init()
    pygame.font.init()
    renderer.screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Environment Render")
    renderer._pygame_initialized = True
    apply_renderer_metrics(renderer, renderer.tile_size)


def ensure_screen_size(renderer: "Pygame_Renderer", width: int, height: int) -> None:
    """Resize the pygame window only when the target dimensions change."""
    desired_size = (width, height)
    if renderer._window_size == desired_size:
        return
    renderer.screen = pygame.display.set_mode(desired_size)
    renderer._window_size = desired_size


# Module-level state for the zero-arg render_step() convenience API
_default_renderer: "Pygame_Renderer | None" = None


def render_step(
    env,
    *,
    renderer: "Pygame_Renderer | None" = None,
    step_delay: float = 0.0,
    sidebar_agent_id: int = 0,
) -> bool:
    """Render one frame, pump events, return False if the window was closed.

    This is the single function to call inside any experiment step loop.
    It handles: initializing pygame (first call), rendering the full frame
    (background, entities, effects, HUD), pumping the event queue, and
    detecting window close / ESC.

    Args:
        env: The environment to render.
        renderer: An existing ``Pygame_Renderer`` to reuse across calls.
            If *None*, one is created automatically on the first call and
            reused for the lifetime of the process.
        step_delay: Seconds to sleep after displaying the frame (useful
            for slowing down autoplay).
        sidebar_agent_id: Which agent's policy info to show in the
            sidebar (only used when the env has a HUD sidebar).

    Returns:
        True if the window is still open, False if the user closed it.

    Usage — zero-config (auto-creates renderer)::

        from word_play.presets.renderers import render_step

        for step in range(100):
            actions = [agent.get_component(Agent_Policy).select_action(env.observe(i))[0]
                       for i, agent in enumerate(env.agents)]
            env.step(actions)
            if not render_step(env): break

    Usage — custom renderer (pass your own layout / tile size)::

        from word_play.presets.renderers import Pygame_Renderer, Grid_Layout_Adapter, render_step

        renderer = Pygame_Renderer(layout=Grid_Layout_Adapter(), tile_size=56)

        for step in range(100):
            # ... env.step(actions) ...
            if not render_step(env, renderer=renderer, step_delay=0.3): break
    """
    from word_play.core.components import Agent_Policy
    from .draw import render_environment
    from .hud import apply_policy_selection_sidebar
    from .layout import Environment_Layout_Adapter
    from .renderer import Pygame_Renderer

    global _default_renderer

    rend = renderer or _default_renderer
    if rend is None:
        rend = Pygame_Renderer(layout=Environment_Layout_Adapter(), tile_size=56)
        _default_renderer = rend

    if not rend._pygame_initialized:
        init_pygame_if_needed(rend)

    # Auto-populate sidebar from the selected agent's last policy info
    if env.agents and 0 <= sidebar_agent_id < len(env.agents):
        agent = env.agents[sidebar_agent_id]
        policy = agent.get_component(Agent_Policy)
        last_info = getattr(policy, "_last_info", None)
        if last_info is not None:
            obs = env.observe(sidebar_agent_id)
            apply_policy_selection_sidebar(
                env,
                observation=obs,
                selection=last_info.get("_last_action", ""),
                info=last_info,
            )

    render_environment(rend, env)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            if rend is _default_renderer:
                _default_renderer = None
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            pygame.quit()
            if rend is _default_renderer:
                _default_renderer = None
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r and hasattr(env, "reset"):
            env.reset()

    if step_delay > 0:
        time.sleep(step_delay)

    return True
