"""Render every SinglePointLayout preset to a PNG for visual iteration.

    PYTHONPATH=src:. .venv/bin/python scripts/render_single_point_presets.py --agents 7
"""
from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pygame

import word_play.presets.renderers  # noqa: F401  (import package first)
from word_play.core import Entity, Environment, Observation
from word_play.presets.action_policies.random_action import Random_Action_Policy
from word_play.presets.movement.single_point import SINGLE_POINT_MOVEMENT_SYSTEM, Single_Point_Position
from word_play.presets.renderers import Pygame_Renderer
from word_play.presets.renderers.single_point_renderer import SinglePointLayout
from word_play.presets.renderers.pygame_renderer.renderable import Renderable
from word_play.presets.systems.do_nothing import Do_Nothing

_HUMANS = [
    "boatman", "archmage", "blacksmith", "elf_lord", "knight_errant",
    "merchant", "monk", "noblewoman", "sage", "guardswoman", "diplomat", "scholar",
]
_HUMAN_DIR = "sprite_library/src/characters/humanoids/human"


def _human_sprite(i: int) -> str:
    # Fall back through the directory if a preferred name is missing.
    preferred = ROOT / _HUMAN_DIR / f"{_HUMANS[i % len(_HUMANS)]}.png"
    if preferred.exists():
        return f"{_HUMAN_DIR}/{preferred.name}"
    options = sorted((ROOT / _HUMAN_DIR).glob("*.png"))
    return f"{_HUMAN_DIR}/{options[i % len(options)].name}"


class SinglePointEnv(Environment):
    def __init__(self, n: int, renderer=None):
        entities = [
            Entity(
                name=f"Agent {i + 1}",
                position=Single_Point_Position(),
                actions=[Do_Nothing()],
                components=[Random_Action_Policy(), Renderable(_human_sprite(i), z_index=100)],
            )
            for i in range(n)
        ]
        super().__init__(
            description="single point preset preview",
            entities=entities,
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=lambda actions, env: [0.0 for _ in env.agents],
            entity_order=lambda ents, env: list(range(len(ents))),
            renderer=renderer,
        )

    def observe(self, agent_id: int) -> Observation:
        return Observation()

    def environment_start_of_step(self, action_selections):
        return None

    def environment_end_of_step(self, action_selections):
        return None

    def _reset(self, seed=None):
        return None


class CapturingRenderer(Pygame_Renderer):
    def create_renderer_state(self):
        state = super().create_renderer_state()
        state.frame["ui.hud_visible"] = False
        return state

    def present(self, env) -> None:
        super().present(env)
        self.captured = self._compose()

    def _compose(self):
        if not hasattr(self, "floor_surface"):
            return None
        w, h = self.floor_surface.get_width(), self.floor_surface.get_height()
        surface = pygame.Surface((w, h))
        surface.fill((18, 20, 26))
        floor = self.floor_surface.copy()
        floor.set_colorkey((8, 11, 16))
        surface.blit(floor, (0, 0))
        surface.blit(self.shadow_surface, (0, 0))
        surface.blit(self.entity_surface, (0, 0))
        if hasattr(self, "effect_surface"):
            surface.blit(self.effect_surface, (0, 0))
        return surface


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=7)
    ap.add_argument("--tile-size", type=int, default=48)
    ap.add_argument("--modes", default="ring,compass,boardroom,horseshoe,auditorium,debate")
    ap.add_argument("--out-dir", default="docs/single_point_previews")
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    for mode in args.modes.split(","):
        mode = mode.strip()
        layout = SinglePointLayout(mode)
        renderer = CapturingRenderer(
            layout=layout,
            tile_size=args.tile_size,
            default_floor_sprite=getattr(layout, "DEFAULT_FLOOR",
                                         "sprite_library/src/world_tiles/indoors/floors/day_brick_floor_c.png"),
        )
        env = SinglePointEnv(args.agents, renderer=renderer)
        env.render()
        surface = getattr(renderer, "captured", None)
        if surface is None:
            print(f"{mode}: no frame")
            continue
        path = out_dir / f"{mode}.png"
        pygame.image.save(surface, str(path))
        print(f"{mode}: {path.relative_to(ROOT)} ({surface.get_width()}x{surface.get_height()})")


if __name__ == "__main__":
    main()
