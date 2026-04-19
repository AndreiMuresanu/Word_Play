from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    import pygame
except ImportError:  # pragma: no cover - exercised only when pygame is absent.
    pygame = None

from word_play.presets.environments import KitchenLayoutAdapter, OvercookedKitchenEnv
from word_play.core import Entity
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.renderers import Pygame_Renderer, Renderable
from word_play.utils import ExperimentRecorder


class ReplayFrameEnvironment:
    def __init__(self, frame: dict[str, Any]):
        self.description = frame.get("description", "Replay Frame")
        self.tick = frame.get("tick", 0)
        self.score = frame.get("score", 0)
        self.deliveries = frame.get("deliveries", 0)
        self.event_log = list(frame.get("event_log", []))
        self.hud_lines = list(frame.get("hud_lines", []))
        self._background_tiles = list(frame.get("background_tiles", []))
        self.state = SimpleNamespace(entities=self._build_entities(frame.get("entities", [])))

    def _build_entities(self, entities: list[dict[str, Any]]) -> list[Entity]:
        built: list[Entity] = []
        for entity in entities:
            x = entity.get("x")
            y = entity.get("y")
            if x is None or y is None:
                continue
            renderable_info = entity.get("renderable") or {}
            renderable = Renderable(sprite_path=renderable_info.get("sprite_path"),
                z_index=renderable_info.get("z_index", 0),
                visible=renderable_info.get("visible", True),
                overlay_sprite=renderable_info.get("overlay_sprite") or entity.get("overlay"),
                overlay_mode=renderable_info.get("overlay_mode", "badge"),
                overlay_scale=renderable_info.get("overlay_scale"),
                foreground_sprite=renderable_info.get("foreground_sprite"),
                foreground_scale=renderable_info.get("foreground_scale"),
                shadow_scale=renderable_info.get("shadow_scale", 0.72),
                bob_amplitude=renderable_info.get("bob_amplitude", 0.0),
                bob_speed=renderable_info.get("bob_speed", 1.6),
                animation_frames=renderable_info.get("animation_frames"),
                animation_fps=renderable_info.get("animation_fps", 5.0),
                emissive_sprite=renderable_info.get("emissive_sprite"),
                emissive_intensity=renderable_info.get("emissive_intensity", 84),
            )
            built.append(
                Entity(
                    name=entity["name"],
                    position=Position_2D(int(x), int(y)),
                    tags=list(entity.get("tags", [])),
                    components=[renderable],
                )
            )
        return built

    def background_tiles(self) -> list[dict[str, Any]]:
        return list(self._background_tiles)


def _apply_replay_hud(frame: dict[str, Any], frame_index: int, frame_count: int, playing: bool, fps: float) -> None:
    action_lines = [f"{item['actor_name']}: {item['label']}" for item in frame.get("selected_actions", [])]
    note_lines = list(frame.get("notes", []))
    frame["hud_lines"] = [
        f"Replay {frame_index + 1}/{frame_count} {'PLAY' if playing else 'PAUSE'}  speed {fps:.1f} fps",
        "Controls: space play/pause, left/right step, up/down speed, home/end jump, esc quit",
        *(action_lines[:1] or note_lines[:1] or ["No recorded action for this frame."]),
        *(note_lines[1:2]),
    ]


def run_overcooked_replay(
    log_path: str | Path,
    *,
    tile_size: int = 56,
    fps: float = 2.0,
) -> None:
    if pygame is None:
        raise ImportError("pygame is required for replay. Run `pip install pygame`.")

    if str(log_path).endswith(".pkl"):
        payload = pickle.loads(Path(log_path).read_bytes())
    else:
        payload = json.loads(Path(log_path).read_text(encoding="utf-8"))
    frames = payload["frames"]
    if not frames:
        raise ValueError("Replay log is empty.")

    renderer = Pygame_Renderer(layout=KitchenLayoutAdapter(), tile_size=tile_size)
    clock = pygame.time.Clock()
    frame_index = 0
    playing = False
    last_advance = time.monotonic()

    while True:
        now = time.monotonic()
        if playing and now - last_advance >= 1.0 / max(fps, 0.25):
            frame_index = min(frame_index + 1, len(frames) - 1)
            last_advance = now
            if frame_index >= len(frames) - 1:
                playing = False

        frame = dict(frames[frame_index])
        _apply_replay_hud(frame, frame_index, len(frames), playing, fps)
        renderer.render(ReplayFrameEnvironment(frame))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                return
            if event.key == pygame.K_SPACE:
                playing = not playing
                last_advance = time.monotonic()
            elif event.key == pygame.K_RIGHT:
                frame_index = min(frame_index + 1, len(frames) - 1)
                playing = False
            elif event.key == pygame.K_LEFT:
                frame_index = max(frame_index - 1, 0)
                playing = False
            elif event.key == pygame.K_HOME:
                frame_index = 0
                playing = False
            elif event.key == pygame.K_END:
                frame_index = len(frames) - 1
                playing = False
            elif event.key == pygame.K_UP:
                fps = min(fps + 0.5, 12.0)
            elif event.key == pygame.K_DOWN:
                fps = max(fps - 0.5, 0.5)

        clock.tick(60)


def _selection_lines(agent_name: str, actions: list[str], selected_index: int) -> list[str]:
    lines = [f"{agent_name} choices:"]
    start = max(0, selected_index - 1)
    end = min(len(actions), selected_index + 3)
    for idx in range(start, end):
        prefix = ">" if idx == selected_index else " "
        lines.append(f"{prefix} {idx}: {actions[idx]}")
    return lines


def _collect_required_kwargs(step_actions) -> None:
    for selection in step_actions:
        if not selection.required_kwargs:
            selection.action_kwargs = {}
            continue

        print(f"\n{selection.actor.name} -> {selection}")
        print("Required arguments:")
        for name, arg in selection.required_kwargs.items():
            desc = arg.arg_description(selection.actor, selection.target_entity, selection.env)
            print(f"  - {name}: {desc}")

        while True:
            raw = input("Enter values separated by ';' before the next frame: ").strip()
            try:
                selection.action_kwargs = selection.parse_and_validate_kwarg_list(raw)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"Invalid input: {exc}")


def run_interactive_overcooked(
    *,
    tile_size: int = 56,
    record_path: str | None = None,
) -> None:
    if pygame is None:
        raise ImportError("pygame is required for interactive-overcooked. Run `pip install pygame`.")

    renderer = Pygame_Renderer(layout=KitchenLayoutAdapter(), tile_size=tile_size)
    env = OvercookedKitchenEnv(renderer=renderer)
    recorder = None if record_path is None else ExperimentRecorder(record_path, title="Interactive Overcooked Session")
    if recorder is not None:
        recorder.record(env, frame_type="initial", notes=["Interactive pygame session ready."])

    selected_agent = 0
    selected_actions = [0 for _ in env.agents]
    clock = pygame.time.Clock()

    while True:
        active_agent = env.agents[selected_agent]
        active_possible_actions = env.possible_actions(active_agent)
        if active_possible_actions:
            selected_actions[selected_agent] = min(selected_actions[selected_agent], len(active_possible_actions) - 1)

        hud_lines = [
            "Controls: tab switch agent, up/down choose action, enter commit frame, esc quit",
            f"Active chef: {active_agent.name}",
        ]
        for agent_index, agent in enumerate(env.agents):
            possible_actions = env.possible_actions(agent)
            choice_idx = min(selected_actions[agent_index], max(0, len(possible_actions) - 1))
            if possible_actions:
                label = str(possible_actions[choice_idx])
            else:
                label = "<no valid actions>"
            marker = "*" if agent_index == selected_agent else "-"
            hud_lines.append(f"{marker} {agent.name}: {label}")

        if active_possible_actions:
            hud_lines.extend(_selection_lines(active_agent.name, [str(action) for action in active_possible_actions], selected_actions[selected_agent]))

        env.hud_lines = hud_lines[:5]
        env.render()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                return
            if event.key == pygame.K_TAB:
                selected_agent = (selected_agent + 1) % len(env.agents)
            elif event.key == pygame.K_UP:
                possible_actions = env.possible_actions(env.agents[selected_agent])
                if possible_actions:
                    selected_actions[selected_agent] = (selected_actions[selected_agent] - 1) % len(possible_actions)
            elif event.key == pygame.K_DOWN:
                possible_actions = env.possible_actions(env.agents[selected_agent])
                if possible_actions:
                    selected_actions[selected_agent] = (selected_actions[selected_agent] + 1) % len(possible_actions)
            elif event.key in {pygame.K_RETURN, pygame.K_SPACE}:
                step_actions = []
                for agent_index, agent in enumerate(env.agents):
                    possible_actions = env.possible_actions(agent)
                    if not possible_actions:
                        raise ValueError(f"Agent '{agent.name}' has no valid actions.")
                    selection = possible_actions[selected_actions[agent_index] % len(possible_actions)]
                    step_actions.append(selection)
                _collect_required_kwargs(step_actions)
                env.step(step_actions)
                if recorder is not None:
                    recorder.record(
                        env,
                        selected_actions=step_actions,
                        frame_type="step",
                        notes=[f"{selection.actor.name}: {selection}" for selection in step_actions],
                    )
                selected_actions = [0 for _ in env.agents]

        clock.tick(60)


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pygame viewers for Word Play environments and experiment replays.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    replay_parser = subparsers.add_parser("replay", help="Play a recorded experiment log in pygame.")
    replay_parser.add_argument("log_path")
    replay_parser.add_argument("--tile-size", type=int, default=56)
    replay_parser.add_argument("--fps", type=float, default=2.0)

    interactive_parser = subparsers.add_parser("interactive-overcooked", help="Run a human-playable overcooked session in pygame.")
    interactive_parser.add_argument("--tile-size", type=int, default=56)
    interactive_parser.add_argument("--record", default=None)

    return parser


def main() -> None:
    args = _build_cli().parse_args()
    if args.mode == "replay":
        run_overcooked_replay(args.log_path, tile_size=args.tile_size, fps=args.fps)
        return

    run_interactive_overcooked(tile_size=args.tile_size, record_path=args.record)


if __name__ == "__main__":
    main()
