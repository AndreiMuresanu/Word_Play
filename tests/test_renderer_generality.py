"""Phase-2 generality: chrome styles."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from word_play.presets.renderers.pygame_renderer.chrome import CHROMES, RUSTIC, resolve_chrome


def test_three_chromes_ship_and_unknown_falls_back():
    assert {"rustic", "slate", "minimal"} <= set(CHROMES)
    assert resolve_chrome("slate").name == "slate"
    assert resolve_chrome("no_such_style") is RUSTIC
    assert resolve_chrome(None) is RUSTIC

