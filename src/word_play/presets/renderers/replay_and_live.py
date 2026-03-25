from __future__ import annotations

import pickle
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

from word_play.core import Entity
from word_play.presets.movement.simple_2d_grid import Position_2D

from .draw import render_environment
from .renderer import Renderable
from .runtime import init_pygame_if_needed

if TYPE_CHECKING:
    from word_play.core import Action_Selection, Environment

    from .renderer import PygameRenderer


NUMERIC_OPTION_KEYS = {} if pygame is None else {
    pygame.K_1: 0,
    pygame.K_2: 1,
    pygame.K_3: 2,
    pygame.K_4: 3,
    pygame.K_5: 4,
    pygame.K_6: 5,
    pygame.K_7: 6,
    pygame.K_8: 7,
    pygame.K_9: 8,
    pygame.K_KP1: 0,
    pygame.K_KP2: 1,
    pygame.K_KP3: 2,
    pygame.K_KP4: 3,
    pygame.K_KP5: 4,
    pygame.K_KP6: 5,
    pygame.K_KP7: 6,
    pygame.K_KP8: 7,
    pygame.K_KP9: 8,
}


class ReplayFrameEnvironment:
    def __init__(self, frame: dict[str, Any]):
        self.description = frame.get("description", "Replay Frame")
        self.tick = frame.get("tick", 0)
        self.score = frame.get("score", 0)
        self.deliveries = frame.get("deliveries", 0)
        self.speech_bubble_sprite = frame.get("speech_bubble_sprite")
        self.speech_bubbles = list(frame.get("speech_bubbles", []))
        self.event_log = list(frame.get("event_log", []))
        self.hud_header = frame.get("hud_header")
        self.hud_lines = list(frame.get("hud_lines", []))
        self.draw_grid_overlay = bool(frame.get("draw_grid_overlay", False))
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
            built.append(
                Entity(
                    name=entity["name"],
                    position=Position_2D(int(x), int(y)),
                    tags=list(entity.get("tags", [])),
                    components=[
                        Renderable(
                            sprite_path=renderable_info.get("sprite_path"),
                            z_index=renderable_info.get("z_index", 0),
                            visible=renderable_info.get("visible", True),
                            overlay_sprite=renderable_info.get("overlay_sprite"),
                            overlay_mode=renderable_info.get("overlay_mode", "badge"),
                            overlay_scale=renderable_info.get("overlay_scale"),
                        )
                    ],
                )
            )
        return built

    def background_tiles(self) -> list[dict[str, Any]]:
        return list(self._background_tiles)


def selection_label(selection: "Action_Selection") -> str:
    return f"{selection.actor.name}: {selection}"


def prompt_options_for_arg(selection: "Action_Selection", arg_name: str, arg: Any) -> list[tuple[str, Any]]:
    if hasattr(arg, "choices"):
        choices = sorted(getattr(arg, "choices"), key=str)
        return [(str(choice), choice) for choice in choices]

    parser_name = arg.__class__.__name__.lower()
    if "bool" in parser_name:
        return [("true", True), ("false", False)]

    raise ValueError(
        f"Pygame prompt only supports choice-like arguments right now. "
        f"Could not build numeric options for '{arg_name}' on '{selection}'."
    )


def build_pending_prompt(
    step_actions: list["Action_Selection"],
    *,
    resume_play: bool,
) -> dict[str, Any] | None:
    prompt_queue: list[dict[str, Any]] = []
    for selection_index, selection in enumerate(step_actions):
        if not selection.required_kwargs or selection.action_kwargs:
            continue
        for arg_name, arg in selection.required_kwargs.items():
            prompt_queue.append(
                {
                    "selection_index": selection_index,
                    "arg_name": arg_name,
                    "arg": arg,
                    "options": prompt_options_for_arg(selection, arg_name, arg),
                }
            )

    if not prompt_queue:
        return None

    return {
        "step_actions": step_actions,
        "prompt_queue": prompt_queue,
        "prompt_index": 0,
        "resume_play": resume_play,
    }


def active_prompt_entry(pending_prompt: dict[str, Any]) -> dict[str, Any]:
    return pending_prompt["prompt_queue"][pending_prompt["prompt_index"]]


def apply_prompt_choice(pending_prompt: dict[str, Any], option_index: int) -> bool:
    prompt_entry = active_prompt_entry(pending_prompt)
    options = prompt_entry["options"]
    if option_index < 0 or option_index >= len(options):
        return False

    selection = pending_prompt["step_actions"][prompt_entry["selection_index"]]
    selection.action_kwargs = selection.action_kwargs or {}
    _, value = options[option_index]
    selection.action_kwargs[prompt_entry["arg_name"]] = value
    pending_prompt["prompt_index"] += 1
    return pending_prompt["prompt_index"] >= len(pending_prompt["prompt_queue"])


def apply_live_hud(
    env: "Environment",
    *,
    paused: bool,
    step_cursor: int,
    total_steps: int,
    pending_prompt: dict[str, Any] | None = None,
) -> None:
    if pending_prompt is not None:
        prompt_entry = active_prompt_entry(pending_prompt)
        selection = pending_prompt["step_actions"][prompt_entry["selection_index"]]
        arg = prompt_entry["arg"]
        options = prompt_entry["options"]
        prompt_number = pending_prompt["prompt_index"] + 1
        total_prompts = len(pending_prompt["prompt_queue"])
        env.hud_header = f"INPUT REQUIRED   Step: {getattr(env, 'tick', 0)}   Prompt {prompt_number}/{total_prompts}"
        env.hud_lines = [
            f"{selection.actor.name}: {selection}",
            f"Choose {prompt_entry['arg_name']} ({arg.arg_description(selection.actor, selection.target_entity, selection.env)})",
            *(f"{index + 1}. {label}" for index, (label, _) in enumerate(options[:4])),
            "Press a number key to continue.",
        ]
        return

    mode = "WAIT" if paused else "LIVE"
    selected_preview = []
    for agent in getattr(env, "agents", []):
        possible_actions = env.possible_actions(agent)
        selected_preview.append(f"{agent.name}: {possible_actions[0] if possible_actions else '<no valid actions>'}")

    orders_line = f"Orders: {env.order_summary()}" if hasattr(env, "order_summary") else None
    health_line = f"Health: {env.health_summary()}" if hasattr(env, "health_summary") else None
    env.hud_header = (
        f"Score: {getattr(env, 'score', 0)}   Step: {getattr(env, 'tick', 0)}   "
        f"Deliveries: {getattr(env, 'deliveries', 0)}   {mode}"
    )
    env.hud_lines = [
        "Live view: Esc quit, R reset, Enter advance when waiting.",
        f"Progress: step {step_cursor}/{total_steps}",
        *([orders_line] if orders_line else []),
        *([health_line] if health_line else []),
        *(selected_preview[:2] or ["No agent actions available."]),
        *(list(getattr(env, "event_log", []))[-2:] or ["Environment ready."]),
    ]


def apply_replay_hud(frame: dict[str, Any], frame_index: int, frame_count: int, paused: bool) -> None:
    action_lines = [f"{item['actor_name']}: {item['label']}" for item in frame.get("selected_actions", [])]
    note_lines = list(frame.get("notes", []))
    frame["hud_header"] = (
        f"Score: {frame.get('score', 0)}   Step: {frame.get('tick', 0)}   "
        f"Deliveries: {frame.get('deliveries', 0)}   REPLAY"
    )
    frame["hud_lines"] = [
        "Controls: space play/pause, left/right look back, home/end jump, enter step, r reset, esc quit",
        f"Timeline: replay frame {frame_index + 1}/{frame_count} {'PAUSE' if paused else 'LIVE'}",
        *(action_lines[:2] or note_lines[:2] or ["No recorded action for this frame."]),
        *(note_lines[2:3]),
    ]


def capture_frame(
    renderer: "PygameRenderer",
    env: "Environment",
    *,
    selected_actions: list["Action_Selection"] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
) -> dict[str, Any]:
    from word_play.utils.interactive_env import capture_environment_frame

    return capture_environment_frame(
        env,
        selected_actions=selected_actions,
        notes=notes,
        frame_type=frame_type,
        draw_grid_overlay=getattr(env, "draw_grid_overlay", renderer.default_draw_grid_overlay),
    )


def record_frame(
    renderer: "PygameRenderer",
    env: "Environment",
    *,
    frames: list[dict[str, Any]],
    recorder: Any | None = None,
    selected_actions: list["Action_Selection"] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
) -> list[dict[str, Any]]:
    frame = capture_frame(renderer, env, selected_actions=selected_actions, notes=notes, frame_type=frame_type)
    frames.append(frame)
    if recorder is not None:
        recorder.record(
            env,
            selected_actions=selected_actions,
            notes=notes,
            frame_type=frame_type,
            draw_grid_overlay=getattr(env, "draw_grid_overlay", renderer.default_draw_grid_overlay),
        )
    return frames


def step_and_record(
    renderer: "PygameRenderer",
    env: "Environment",
    *,
    frames: list[dict[str, Any]],
    recorder: Any | None,
    step_actions: list["Action_Selection"],
) -> list[dict[str, Any]]:
    env.step(step_actions)
    return record_frame(
        renderer,
        env,
        frames=frames,
        recorder=recorder,
        selected_actions=step_actions,
        frame_type="step",
        notes=[selection_label(selection) for selection in step_actions],
    )


def make_recorder(
    log_path: str | Path | None,
    *,
    title: str,
    metadata: dict[str, Any] | None = None,
    keep_logs: bool = True,
    log_root: str | Path | None = None,
) -> Any | None:
    if not keep_logs:
        return None

    from word_play.utils import ExperimentRecorder, default_experiment_log_path

    resolved_path = Path(log_path) if log_path is not None else default_experiment_log_path(title, root_dir=log_root)
    return ExperimentRecorder(resolved_path, title=title, metadata=metadata)


def episode_done(env: "Environment") -> bool:
    terminations = list(getattr(env, "terminations", []))
    truncations = list(getattr(env, "truncations", []))
    return bool(terminations) and (all(terminations) or all(truncations))


def load_recording_payload(log_path: str | Path) -> dict[str, Any]:
    return pickle.loads(Path(log_path).read_bytes())


def replay_frames(
    renderer: "PygameRenderer",
    frames: list[dict[str, Any]],
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    init_pygame_if_needed(renderer)
    if not frames:
        raise ValueError("Replay log is empty.")

    clock = pygame.time.Clock()
    paused = not autoplay
    viewing_index = 0
    last_advance = time.monotonic()

    while True:
        frame = dict(frames[viewing_index])
        apply_replay_hud(frame, viewing_index, len(frames), paused)
        render_environment(renderer, ReplayFrameEnvironment(frame))

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
                paused = not paused
                last_advance = time.monotonic()
            elif event.key == pygame.K_RIGHT:
                paused = True
                viewing_index = min(len(frames) - 1, viewing_index + 1)
            elif event.key == pygame.K_LEFT:
                paused = True
                viewing_index = max(0, viewing_index - 1)
            elif event.key == pygame.K_HOME:
                paused = True
                viewing_index = 0
            elif event.key == pygame.K_END:
                paused = True
                viewing_index = len(frames) - 1

        if not paused and time.monotonic() - last_advance >= step_delay:
            if viewing_index >= len(frames) - 1:
                paused = True
            else:
                viewing_index += 1
                last_advance = time.monotonic()

        clock.tick(60)


def replay_recording(
    renderer: "PygameRenderer",
    log_path: str | Path,
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    payload = load_recording_payload(log_path)
    replay_frames(
        renderer,
        payload.get("frames", []),
        autoplay=autoplay,
        step_delay=step_delay,
    )


def run_live_view(
    renderer: "PygameRenderer",
    env: "Environment",
    *,
    step_builder: Callable[["Environment"], list["Action_Selection"]],
    recorder: Any | None = None,
    keep_logs: bool = True,
    log_path: str | Path | None = None,
    log_root: str | Path | None = None,
    record_title: str = "Environment Replay",
    record_metadata: dict[str, Any] | None = None,
    autoplay: bool = True,
    step_delay: float = 0.28,
    max_steps: int | None = None,
    reset_factory: Callable[[], "Environment"] | None = None,
    initial_notes: list[str] | None = None,
    autofill_required_kwargs: Callable[["Action_Selection"], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    init_pygame_if_needed(renderer)
    recorder = recorder or make_recorder(
        log_path,
        title=record_title,
        metadata=record_metadata,
        keep_logs=keep_logs,
        log_root=log_root,
    )
    renderer.last_record_path = None if recorder is None else str(recorder.output_path)

    frames: list[dict[str, Any]] = []
    frames = record_frame(
        renderer,
        env,
        frames=frames,
        recorder=recorder,
        frame_type="initial",
        notes=list(initial_notes or ["Viewer booted."]),
    )

    total_steps = max_steps if max_steps is not None else getattr(env, "episode_length", len(frames))
    committed_steps = 0

    clock = pygame.time.Clock()
    paused = not autoplay
    last_step_at = time.monotonic()
    pending_prompt: dict[str, Any] | None = None

    while True:
        apply_live_hud(
            env,
            paused=paused,
            step_cursor=committed_steps,
            total_steps=total_steps,
            pending_prompt=pending_prompt,
        )
        render_environment(renderer, env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return frames
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                return frames
            if pending_prompt is not None:
                chosen_index = NUMERIC_OPTION_KEYS.get(event.key)
                if chosen_index is None:
                    continue
                if not apply_prompt_choice(pending_prompt, chosen_index):
                    continue
                frames = step_and_record(
                    renderer,
                    env,
                    frames=frames,
                    recorder=recorder,
                    step_actions=pending_prompt["step_actions"],
                )
                committed_steps += 1
                last_step_at = time.monotonic()
                paused = not pending_prompt["resume_play"]
                pending_prompt = None
                continue

            if event.key == pygame.K_r and reset_factory is not None:
                env = reset_factory()
                frames = []
                frames = record_frame(
                    renderer,
                    env,
                    frames=frames,
                    recorder=recorder,
                    frame_type="initial",
                    notes=["Viewer reset."],
                )
                paused = not autoplay
                committed_steps = 0
                last_step_at = time.monotonic()
                pending_prompt = None
            elif event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and committed_steps < total_steps:
                step_actions = step_builder(env)
                prompt_state = build_pending_prompt(step_actions, resume_play=False)
                if prompt_state is None:
                    frames = step_and_record(
                        renderer,
                        env,
                        frames=frames,
                        recorder=recorder,
                        step_actions=step_actions,
                    )
                    committed_steps += 1
                    last_step_at = time.monotonic()
                    paused = True
                else:
                    pending_prompt = prompt_state
                    paused = True

        if pending_prompt is None and not paused and committed_steps < total_steps and not episode_done(env):
            now = time.monotonic()
            if now - last_step_at >= step_delay:
                step_actions = step_builder(env)
                prompt_state = build_pending_prompt(step_actions, resume_play=True)
                if prompt_state is None:
                    frames = step_and_record(
                        renderer,
                        env,
                        frames=frames,
                        recorder=recorder,
                        step_actions=step_actions,
                    )
                    committed_steps += 1
                    last_step_at = now
                else:
                    pending_prompt = prompt_state
                    paused = True

        clock.tick(60)

    return frames
