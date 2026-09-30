"""Phase-2 generality: chrome styles."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from word_play.presets.renderers.pygame_renderer.chrome import CHROMES, RUSTIC, resolve_chrome
from word_play.presets.renderers.pygame_renderer.renderable import Renderable


def test_three_chromes_ship_and_unknown_falls_back():
    assert {"rustic", "slate", "minimal"} <= set(CHROMES)
    assert resolve_chrome("slate").name == "slate"
    assert resolve_chrome("no_such_style") is RUSTIC
    assert resolve_chrome(None) is RUSTIC


def test_renderable_accepts_tint():
    renderable = Renderable(sprite_path="sheep", tint=(220, 60, 60), tint_strength=0.7)
    assert renderable.tint == (220, 60, 60)
    assert renderable.tint_strength == 0.7

