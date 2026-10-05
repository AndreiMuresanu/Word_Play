"""Phase-2 generality: chrome styles, sprite index, graceful degradation."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from word_play.presets.renderers.pygame_renderer.chrome import CHROMES, RUSTIC, resolve_chrome
from word_play.presets.renderers.sprite_index import sprite_index, sprite_path_for_name
from word_play.presets.renderers.dynamic_behaviours import resolve_dynamic_behaviour
from word_play.presets.renderers.themes import (
    MISSING_ROLE_PREFIX,
    apply_theme_defaults,
    available_themes,
    resolve_sprite,
    resolve_theme,
)
from word_play.presets.renderers.pygame_renderer.renderable import Renderable


def test_three_chromes_ship_and_unknown_falls_back():
    assert {"rustic", "slate", "minimal"} <= set(CHROMES)
    assert resolve_chrome("slate").name == "slate"
    assert resolve_chrome("no_such_style") is RUSTIC
    assert resolve_chrome(None) is RUSTIC


def test_sprite_index_finds_legacy_art_by_plain_name():
    index = sprite_index()
    assert len(index) > 1000  # the whole library is addressable
    path = sprite_path_for_name("sheep")
    assert path is not None and path.endswith(".png")


def test_sprite_index_is_exact():
    assert sprite_path_for_name("shee") is None           # no silent guessing


def test_bare_name_resolves_without_theme():
    assert resolve_sprite(None, "sheep").endswith(".png")


def test_unknown_name_degrades_to_placeholder_not_crash():
    assert resolve_sprite(None, "zz_totally_not_a_sprite_zz").startswith(MISSING_ROLE_PREFIX)


def test_theme_falls_back_to_index_before_placeholder():
    # "sheep" is not an interactive_city role but exists in the legacy library
    path = resolve_sprite(resolve_theme("interactive_city"), "sheep")
    assert path.endswith(".png") and not path.startswith(MISSING_ROLE_PREFIX)


def test_every_shipped_theme_loads_and_its_sprites_exist():
    root = Path(__file__).resolve().parents[1]
    for name in available_themes():
        theme = resolve_theme(name)
        for role in theme.roles:
            assert (root / theme.sprite(role)).is_file(), (name, role)


def test_theme_defaults_never_rewrite_sprite_path():
    theme = resolve_theme("interactive_city")
    lamp = Renderable(sprite_path="lamp")
    wall = Renderable(sprite_path="wall")
    apply_theme_defaults(lamp, theme)
    apply_theme_defaults(wall, theme)
    assert lamp.sprite_path == "lamp" and lamp.glow is not None
    assert wall.sprite_path == "wall" and wall.wall_set.endswith("timber_wall")


def test_dynamic_behaviour_catalog_covers_archetype_activities():
    for name in (
        "fishing", "mining", "cooking", "cleaning", "planting", "harvesting",
        "carrying", "rowing", "working", "mixing", "repairing", "scanning",
        "attacking", "celebrating", "sitting", "sleeping", "watering",
    ):
        behaviour = resolve_dynamic_behaviour(name)
        assert behaviour is not None, name
        assert behaviour.pose, name


def test_renderable_accepts_tint():
    renderable = Renderable(sprite_path="sheep", tint=(220, 60, 60), tint_strength=0.7)
    assert renderable.tint == (220, 60, 60)
    assert renderable.tint_strength == 0.7


def test_every_theme_renders_a_frame_without_rewriting_sprites():
    from word_play.core import Entity
    from word_play.presets.entity_orderings import randomize_agent_order
    from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
    from word_play.presets.movement.simple_2d_grid import Position_2D
    from word_play.presets.renderers import Grid_Layout_Adapter, Pygame_Renderer

    names = ["tree", "lamp", "wall", "wall", "sheep", "stove"]
    for theme in available_themes():
        renderer = Pygame_Renderer(Grid_Layout_Adapter(), tile_size=24, theme=theme, mood="night")
        entities = [
            Entity(
                name=f"e{i}",
                position=Position_2D(i, 1),
                tags=["wall"] if name == "wall" else [],
                components=[Renderable(sprite_path=name)],
            )
            for i, name in enumerate(names)
        ]
        env = Simple_2D_Grid_World(
            description="render check",
            entities=entities,
            entity_order=randomize_agent_order,
            renderer=renderer,
        )
        env.render()
        env.render()
        assert [e.get_component(Renderable).sprite_path for e in entities] == names, theme


def test_missing_literal_sprite_survives_lit_moods():
    """A literal path that doesn't exist must placeholder, not crash, even when
    the emissive pre-pass runs (any mood with light_level > 0)."""
    from word_play.core.entity import Entity
    from word_play.presets.entity_orderings import randomize_agent_order
    from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
    from word_play.presets.movement.simple_2d_grid import Position_2D
    from word_play.presets.renderers import Grid_Layout_Adapter, Pygame_Renderer

    renderer = Pygame_Renderer(Grid_Layout_Adapter(), tile_size=24, mood="night")
    ghost = Entity(
        name="ghost",
        position=Position_2D(1, 1),
        components=[Renderable(sprite_path="does/not/exist.png")],
    )
    env = Simple_2D_Grid_World(
        description="missing art",
        entities=[ghost],
        entity_order=randomize_agent_order,
        renderer=renderer,
    )
    env.render()
    env.render()
