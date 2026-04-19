from __future__ import annotations

import argparse
import pickle
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable

import pygame

from word_play.core import Entity
from word_play.core.components import Component
from word_play.presets.movement.simple_2d_grid import Position_2D

from .draw import render_environment
from .renderer import Renderable
from .runtime import init_pygame_if_needed

if TYPE_CHECKING:
    from word_play.core import Action_Selection, Environment
    from word_play.core.components import Agent_Policy

    from .renderer import Pygame_Renderer


def run_exp(
    *,
    env: "Environment",
    policy: str = "preview",
    tile_size: int | None = None,
    model_name: str | None = None,
    model_key: str | None = None,
    base_url: str | None = None,
    llm_policy_builder: Callable[["Environment", Entity, str], "Agent_Policy"] | None = None,
    sidebar_width: int | None = None,
    record_title: str | None = None,
    initial_notes: list[str] | None = None,
    keep_logs: bool = True,
    log_path: str | Path | None = None,
    log_root: str | Path | None = None,
    autoplay: bool = True,
    step_delay: float = 0.28,
    max_steps: int | None = None,
) -> str | None:
    """Run an experiment with optional LLM policy support."""
    return _run_render_session(
        env=env,
        policy_mode=policy,
        tile_size=tile_size,
        model_name=model_name,
        model_key=model_key,
        base_url=base_url,
        llm_policy_builder=llm_policy_builder,
        sidebar_width=sidebar_width,
        keep_logs=keep_logs,
        log_path=None if log_path is None else str(log_path),
        log_root=None if log_root is None else str(log_root),
        record_title=record_title,
        step_delay=step_delay,
        max_steps=max_steps,
        initial_notes=initial_notes,
    )


NUMERIC_OPTION_KEYS = {
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
    """Rebuild a minimal environment object from a recorded frame snapshot."""
    def __init__(self, frame: dict[str, Any]):
        """Copy frame fields and reconstruct drawable entities for replay."""
        self._agent_names = self._infer_agent_names(frame)
        self.description = frame.get("description", "Replay Frame")
        self.tick = frame.get("tick", 0)
        self.score = frame.get("score", 0)
        self.deliveries = frame.get("deliveries", 0)
        self.terminations = list(frame.get("terminations", []))
        self.truncations = list(frame.get("truncations", []))
        self.final_boss_defeated = bool(frame.get("final_boss_defeated", False))
        self.speech_bubble_sprite = frame.get("speech_bubble_sprite")
        self.speech_bubbles = list(frame.get("speech_bubbles", []))
        self.event_log = list(frame.get("event_log", []))
        self.hit_entity_names = list(frame.get("hit_entity_names", []))
        self.hit_effects = list(frame.get("hit_effects", []))
        self.sight_radius = frame.get("sight_radius")
        if self.sight_radius is None:
            self.sight_radius = self._infer_sight_radius(frame)
        self.hud_header = frame.get("hud_header")
        self.hud_lines = list(frame.get("hud_lines", []))
        self.hud_sidebar_header = frame.get("hud_sidebar_header")
        self.hud_sidebar_lines = list(frame.get("hud_sidebar_lines", []))
        self.hud_sidebar_selected_action = list(frame.get("hud_sidebar_selected_action", []))
        self.hud_sidebar_actions = list(frame.get("hud_sidebar_actions", []))
        self.hud_sidebar_width = frame.get("hud_sidebar_width")
        self.current_phase = frame.get("current_phase")
        self.hide_bottom_hud = bool(frame.get("hide_bottom_hud", False))
        self.draw_grid_overlay = False
        self._visible_tiles = [tuple(tile) for tile in (frame.get("visible_tiles") or [])]
        self._background_tiles = list(frame.get("background_tiles", []))
        entities = self._build_entities(frame.get("entities", []))
        self.state = SimpleNamespace(entities=entities)
        self.agents = [entity for entity in entities if getattr(entity, "is_agent", False)]
        self.player = self.agents[0] if self.agents else None
        if not self.hud_sidebar_selected_action:
            selected_actions = list(frame.get("selected_actions", []))
            chosen_label = selected_actions[0]["label"] if selected_actions else "(no action chosen yet)"
            self.hud_sidebar_selected_action = ["Chosen Action:", chosen_label]
        if not self.hud_sidebar_actions:
            action_lines = ["Possible Actions:"]
            agent_observations = list(frame.get("agent_observations", []))
            if agent_observations:
                action_lines.extend(
                    f"[{idx}] {item.get('label', '')}".rstrip()
                    for idx, item in enumerate(agent_observations[0].get("possible_actions", []))
                )
            if len(action_lines) == 1:
                action_lines.append("(no actions available)")
            self.hud_sidebar_actions = action_lines

    @staticmethod
    def _infer_agent_names(frame: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        for observation in frame.get("agent_observations", []):
            agent_name = observation.get("agent_name")
            if agent_name:
                names.add(str(agent_name))
        for action in frame.get("selected_actions", []):
            actor_name = action.get("actor_name")
            if actor_name:
                names.add(str(actor_name))
        return names

    @staticmethod
    def _infer_sight_radius(frame: dict[str, Any]) -> int | None:
        for observation in frame.get("agent_observations", []):
            text = observation.get("text")
            if not text:
                continue
            match = re.search(r"sight radius is (\d+) tiles", str(text), flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _build_entities(self, entities: list[dict[str, Any]]) -> list[Entity]:
        """Convert serialized entity payloads back into Entity objects."""
        built: list[Entity] = []
        for entity in entities:
            x = entity.get("x")
            y = entity.get("y")
            if x is None or y is None:
                continue
            renderable_info = entity.get("renderable") or {}
            components: list[Any] = []
            if renderable_info:
                components.append(
                    Renderable(
                        sprite_path=renderable_info.get("sprite_path"),
                        z_index=renderable_info.get("z_index", 0),
                        visible=renderable_info.get("visible", True),
                        overlay_sprite=renderable_info.get("overlay_sprite"),
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
                )
            for component_name, component_payload in (entity.get("components") or {}).items():
                if component_name == "Renderable" or not isinstance(component_payload, dict):
                    continue
                component_type = type(str(component_name), (Component,), {})
                component = component_type()
                for field_name, field_value in component_payload.items():
                    setattr(component, field_name, field_value)
                components.append(component)
            built.append(
                Entity(
                    name=entity["name"],
                    position=Position_2D(int(x), int(y)),
                    tags=list(entity.get("tags", [])),
                    components=components,
                )
            )
            built[-1].is_agent = bool(entity.get("is_agent", built[-1].name in self._agent_names or built[-1].is_agent))
        return built

    def background_tiles(self) -> list[dict[str, Any]]:
        """Return the recorded background tiles for the current replay frame."""
        return list(self._background_tiles)

    def visible_tiles(self) -> list[tuple[int, int]]:
        """Return the recorded line-of-sight tiles for the current replay frame."""
        if self._visible_tiles:
            return list(self._visible_tiles)
        if self.player is None or not isinstance(self.sight_radius, int):
            return []
        player_position = getattr(self.player, "position", None)
        if player_position is None:
            return []
        background = self._background_tiles
        xs = [int(item["x"]) for item in background if item.get("x") is not None]
        ys = [int(item["y"]) for item in background if item.get("y") is not None]
        xs.extend(getattr(entity.position, "x", 0) for entity in self.state.entities)
        ys.extend(getattr(entity.position, "y", 0) for entity in self.state.entities)
        if not xs or not ys:
            return []
        return [
            (x, y)
            for y in range(min(ys), max(ys) + 1)
            for x in range(min(xs), max(xs) + 1)
            if max(abs(player_position.x - x), abs(player_position.y - y)) <= self.sight_radius
        ]


def selection_label(selection: "Action_Selection") -> str:
    """Format a recorded action selection for HUD notes and logs."""
    return f"{selection.actor.name}: {selection}"


def prompt_options_for_arg(selection: "Action_Selection", arg_name: str, arg: Any) -> list[tuple[str, Any]]:
    """Build numbered pygame prompt options for a required action argument."""
    if hasattr(arg, "choices"):
        choices = sorted(getattr(arg, "choices"), key=str)
        return [(str(choice), choice) for choice in choices]

    parser_name = arg.__class__.__name__.lower()
    if "bool" in parser_name:
        return [("true", True), ("false", False)]

    # For numeric types (like inventory index), return a default fallback
    # This handles preview/sequence policies that don't specify all kwargs
    # Check for common patterns: "index", "int", or any numeric naming convention
    if "index" in arg_name.lower() or "int" in parser_name or "Index" in arg.__class__.__name__:
        return [("default (0)", 0)]

    # For other types, return a default placeholder
    return [("default", None)]


def build_pending_prompt(
    step_actions: list["Action_Selection"],
    *,
    resume_play: bool,
) -> dict[str, Any] | None:
    """Queue any unresolved required kwargs before a live step can run."""
    prompt_queue: list[dict[str, Any]] = []
    for selection_index, selection in enumerate(step_actions):
        if not selection.required_kwargs or selection.action_kwargs:
            continue
        for arg_name, arg in selection.required_kwargs.items():
            options = prompt_options_for_arg(selection, arg_name, arg)
            prompt_queue.append(
                {
                    "selection_index": selection_index,
                    "arg_name": arg_name,
                    "arg": arg,
                    "options": options,
                }
            )

    if not prompt_queue:
        return None

    # Auto-resolve prompts that have exactly one option (defaults for sequence/auto mode)
    # This allows action sequences to work without interactive prompt selection
    resolved_count = 0
    for prompt_entry in list(prompt_queue):  # Use list() to allow modification during iteration
        options = prompt_entry["options"]
        if len(options) == 1:
            # Auto-apply the single option
            selection = step_actions[prompt_entry["selection_index"]]
            selection.action_kwargs = selection.action_kwargs or {}
            _, value = options[0]
            selection.action_kwargs[prompt_entry["arg_name"]] = value
            prompt_queue.remove(prompt_entry)
            resolved_count += 1

    # If all prompts were resolved, no pending prompt needed
    if not prompt_queue:
        return None

    return {
        "step_actions": step_actions,
        "prompt_queue": prompt_queue,
        "prompt_index": 0,
        "resume_play": resume_play,
    }


def active_prompt_entry(pending_prompt: dict[str, Any]) -> dict[str, Any]:
    """Return the current required-argument prompt being shown to the user."""
    return pending_prompt["prompt_queue"][pending_prompt["prompt_index"]]


def apply_prompt_choice(pending_prompt: dict[str, Any], option_index: int) -> bool:
    """Apply one prompt choice and report whether the prompt queue is finished."""
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
    renderer: "Pygame_Renderer",
    paused: bool,
    step_cursor: int,
    total_steps: int,
    pending_prompt: dict[str, Any] | None = None,
    step_in_flight: bool = False,
) -> None:
    """Populate HUD text for live stepping and required-input prompts."""
    if pending_prompt is not None:
        prompt_entry = active_prompt_entry(pending_prompt)
        selection = pending_prompt["step_actions"][prompt_entry["selection_index"]]
        arg = prompt_entry["arg"]
        options = prompt_entry["options"]
        prompt_number = pending_prompt["prompt_index"] + 1
        total_prompts = len(pending_prompt["prompt_queue"])
        env.hud_header = f"INPUT REQUIRED Step: {getattr(env, 'tick', 0)} Prompt {prompt_number}/{total_prompts}"
        env.hud_lines = [
            f"{selection.actor.name}: {selection}",
            f"Choose {prompt_entry['arg_name']} ({arg.arg_description(selection.actor, selection.target_entity, selection.env)})",
            *(f"{index + 1}. {label}" for index, (label, _) in enumerate(options[:4])),
            "Press a number key to continue.",
        ]
        return

    selected_preview = []
    for agent in getattr(env, "agents", []):
        possible_actions = env.possible_actions(agent)
        selected_preview.append(f"{agent.name}: {possible_actions[0] if possible_actions else '<no valid actions>'}")

    orders_line = f"Orders: {env.order_summary()}" if hasattr(env, "order_summary") else None
    health_line = f"Health: {env.health_summary()}" if hasattr(env, "health_summary") else None
    env.hud_header = (
        f"Score: {getattr(env, 'score', 0)} Step: {getattr(env, 'tick', 0)} LIVE"
    )
    env.hud_lines = [
        "Live view: Esc to exit, R to reset.",
        f"Progress: step {step_cursor}/{total_steps}",
        (
            f"Camera: focus {renderer.camera_focus_entity_name} "
            f"(radius {getattr(env, 'sight_radius', renderer.camera_focus_radius_tiles)})"
            if renderer.camera_focus_entity_name
            else "Camera: full map"
        ),
        (
            f"Inspecting: {renderer.selected_entity_name}"
            if getattr(renderer, "selected_entity_name", None)
            else "Inspecting: none"
        ),
        ("Agent is thinking..." if step_in_flight else "Agent ready."),
        *([orders_line] if orders_line else []),
        *([health_line] if health_line else []),
        *(selected_preview[:2] or ["No agent actions available."]),
        *(list(getattr(env, "event_log", []))[-2:] or ["Environment ready."]),
    ]


def apply_replay_hud(
    frame: dict[str, Any],
    renderer: "Pygame_Renderer",
    frame_index: int,
    frame_count: int,
    paused: bool,
) -> None:
    """Inject replay-specific HUD text into a recorded frame payload."""
    action_lines = [f"{item['actor_name']}: {item['label']}" for item in frame.get("selected_actions", [])]
    note_lines = list(frame.get("notes", []))
    frame["hud_header"] = (
        f"Score: {frame.get('score', 0)} Step: {frame.get('tick', 0)} REPLAY"
    )
    frame["hud_lines"] = [
        "Controls: space play/pause, left/right look back, home/end jump, enter step, r reset, esc quit, click inspect, [ ] resize",
        f"Timeline: replay frame {frame_index + 1}/{frame_count} {'PAUSE' if paused else 'LIVE'}",
        (
            f"Inspecting: {renderer.selected_entity_name}"
            if getattr(renderer, "selected_entity_name", None)
            else "Inspecting: none"
        ),
        *(action_lines[:2] or note_lines[:2] or ["No recorded action for this frame."]),
        *(note_lines[2:3]),
    ]


def handle_entity_click(renderer: "Pygame_Renderer", env: "Environment", mouse_pos: tuple[int, int]) -> None:
    """Select the clicked entity and focus agents; clear selection on empty-space clicks."""
    for entity in getattr(env.state, "entities", []):
        if entity.name not in renderer._last_drawn_entity_rects:
            continue
        rect = renderer._last_drawn_entity_rects[entity.name]
        if rect.collidepoint(mouse_pos):
            renderer.selected_entity_name = entity.name
            renderer.camera_focus_entity_name = entity.name if getattr(entity, "is_agent", False) else None
            sight_radius = getattr(env, "sight_radius", None)
            if renderer.camera_focus_entity_name is not None and isinstance(sight_radius, int):
                renderer.camera_focus_radius_tiles = max(2, sight_radius)
            if renderer.camera_focus_entity_name is None:
                renderer.camera_center = None
            return
    renderer.selected_entity_name = None
    renderer.camera_focus_entity_name = None
    renderer.camera_center = None


def capture_frame(
    renderer: "Pygame_Renderer",
    env: "Environment",
    *,
    selected_actions: list["Action_Selection"] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
) -> dict[str, Any]:
    """Capture the current environment as a serializable replay frame."""
    from word_play.utils.interactive_env import capture_environment_frame

    return capture_environment_frame(
        env,
        selected_actions=selected_actions,
        notes=notes,
        frame_type=frame_type,
        draw_grid_overlay=getattr(env, "draw_grid_overlay", renderer.default_draw_grid_overlay),
    )


def record_frame(
    renderer: "Pygame_Renderer",
    env: "Environment",
    *,
    frames: list[dict[str, Any]],
    recorder: Any | None = None,
    selected_actions: list["Action_Selection"] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
) -> list[dict[str, Any]]:
    """Append one captured frame to memory and optionally flush it to disk."""
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
    renderer: "Pygame_Renderer",
    env: "Environment",
    *,
    frames: list[dict[str, Any]],
    recorder: Any | None,
    step_actions: list["Action_Selection"],
) -> list[dict[str, Any]]:
    """Advance the environment one step and record the resulting frame."""
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
    """Create an experiment recorder unless logging has been disabled."""
    if not keep_logs:
        return None

    from word_play.utils.interactive_env import ExperimentRecorder, default_experiment_log_path

    resolved_path = Path(log_path) if log_path is not None else default_experiment_log_path(title, root_dir=log_root)
    return ExperimentRecorder(resolved_path, title=title, metadata=metadata)


def episode_done(env: "Environment") -> bool:
    """Return whether every agent has terminated or truncated the episode."""
    terminations = list(getattr(env, "terminations", []))
    truncations = list(getattr(env, "truncations", []))
    return bool(terminations) and (all(terminations) or all(truncations))


def load_recording_payload(log_path: str | Path) -> dict[str, Any]:
    """Load the pickled replay payload from disk."""
    return pickle.loads(Path(log_path).read_bytes())


def replay_frames(
    renderer: "Pygame_Renderer",
    frames: list[dict[str, Any]],
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Run the pygame event loop that displays saved replay frames."""
    init_pygame_if_needed(renderer)
    if not frames:
        raise ValueError("Replay log is empty.")

    clock = pygame.time.Clock()
    paused = not autoplay
    viewing_index = 0
    last_advance = time.monotonic()
    renderer.camera_focus_entity_name = None

    while True:
        frame = dict(frames[viewing_index])
        apply_replay_hud(frame, renderer, viewing_index, len(frames), paused)
        replay_env = ReplayFrameEnvironment(frame)
        render_environment(renderer, replay_env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handle_entity_click(renderer, replay_env, event.pos)
                continue
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
    renderer: "Pygame_Renderer",
    log_path: str | Path,
    *,
    autoplay: bool = False,
    step_delay: float = 0.28,
) -> None:
    """Load a recording file and hand its frames to the replay loop."""
    payload = load_recording_payload(log_path)
    replay_frames(
        renderer,
        payload.get("frames", []),
        autoplay=autoplay,
        step_delay=step_delay,
    )


def run_live_view(
    renderer: "Pygame_Renderer",
    env: "Environment",
    *,
    step_builder: Callable[["Environment"], list["Action_Selection"]],
    recorder: Any | None = None,
    keep_logs: bool = True,
    log_path: str | Path | None = None,
    log_root: str | Path | None = None,
    record_title: str = "Environment Replay",
    record_metadata: dict[str, Any] | None = None,
    step_delay: float = 0.28,
    max_steps: int | None = None,
    reset_factory: Callable[[], "Environment"] | None = None,
    initial_notes: list[str] | None = None,
    autofill_required_kwargs: Callable[["Action_Selection"], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run an interactive pygame loop that steps, renders, and records an environment."""
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
    paused = False  # Live mode always starts immediately, no pause option
    last_step_at = time.monotonic()
    pending_prompt: dict[str, Any] | None = None
    step_request_id = 0
    step_worker: threading.Thread | None = None
    step_result: dict[str, Any] | None = None

    def start_step_request(*, resume_play: bool) -> None:
        nonlocal step_request_id, step_worker, step_result
        if step_worker is not None and step_worker.is_alive():
            return
        step_request_id += 1
        request_id = step_request_id
        step_result = None

        def worker() -> None:
            nonlocal step_result
            try:
                actions = step_builder(env)
                step_result = {
                    "request_id": request_id,
                    "resume_play": resume_play,
                    "step_actions": actions,
                    "error": None,
                }
            except Exception as exc:  # pragma: no cover - surfaced in UI loop
                step_result = {
                    "request_id": request_id,
                    "resume_play": resume_play,
                    "step_actions": None,
                    "error": exc,
                }

        step_worker = threading.Thread(target=worker, daemon=True)
        step_worker.start()

    while True:
        apply_live_hud(
            env,
            renderer=renderer,
            paused=paused,
            step_cursor=committed_steps,
            total_steps=total_steps,
            pending_prompt=pending_prompt,
            step_in_flight=step_worker is not None and step_worker.is_alive(),
        )
        render_environment(renderer, env)

        if step_result is not None and step_result["request_id"] == step_request_id:
            result = step_result
            step_result = None
            step_worker = None
            if result["error"] is not None:
                raise result["error"]
            prompt_state = build_pending_prompt(result["step_actions"], resume_play=result["resume_play"])
            if prompt_state is None:
                frames = step_and_record(
                    renderer,
                    env,
                    frames=frames,
                    recorder=recorder,
                    step_actions=result["step_actions"],
                )
                committed_steps += 1
                last_step_at = time.monotonic()
                paused = not result["resume_play"]
            else:
                pending_prompt = prompt_state
                paused = True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return frames
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handle_entity_click(renderer, env, event.pos)
                continue
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

            if event.key == pygame.K_r and hasattr(env, "reset"):
                step_request_id += 1
                step_result = None
                step_worker = None
                env.reset()
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
                renderer.camera_focus_entity_name = None
                renderer.selected_entity_name = None
                renderer.camera_center = None
                renderer._entity_last_positions = {}

        if (
            pending_prompt is None
            and not paused
            and committed_steps < total_steps
            and not episode_done(env)
            and not (step_worker is not None and step_worker.is_alive())
        ):
            now = time.monotonic()
            if now - last_step_at >= step_delay:
                start_step_request(resume_play=True)

        clock.tick(60)

    return frames


def build_policy_step_actions(
    env: "Environment",
    *,
    on_selection: Callable[["Environment", Any, int, "Action_Selection", dict], None] | None = None,
) -> list["Action_Selection"]:
    """Build one action per agent by querying each attached Agent_Policy or Non_Agent_Policy."""
    from word_play.core.components import Agent_Policy, Non_Agent_Policy

    selections: list[Action_Selection] = []
    for agent_id, agent in enumerate(env.agents):
        # Check for Agent_Policy first (LLM policies), then fall back to Non_Agent_Policy (preview/sequence policies)
        policy = agent.get_component(Agent_Policy)
        observation = env.observe(agent_id)
        
        if policy is not None:
            # Agent_Policy: takes observation, returns (Action_Selection, info)
            selection, info = policy.select_action(observation)
        else:
            # Non_Agent_Policy: takes possible_actions and env, returns Action_Selection
            policy = agent.get_component(Non_Agent_Policy)
            if policy is None:
                raise ValueError(f"Agent '{agent.name}' is missing an Agent_Policy or Non_Agent_Policy component.")
            possible_actions = env.possible_actions(agent)
            selection = policy.select_action(possible_actions, env)
            info = {}
        
        if on_selection is not None:
            on_selection(env, observation, agent_id, selection, info)
        selections.append(selection)
    return selections


def run_policy_live_view(
    renderer: "Pygame_Renderer",
    *,
    env: "Environment",
    step_builder: Callable[["Environment"], list["Action_Selection"]] | None = None,
    on_policy_selection: Callable[["Environment", Any, int, "Action_Selection", dict], None] | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """Run the live viewer with policy-driven stepping and env.reset()-based resets."""
    resolved_step_builder = step_builder or (
        lambda env: build_policy_step_actions(env, on_selection=on_policy_selection)
    )
    return run_live_view(
        renderer,
        env,
        step_builder=resolved_step_builder,
        **kwargs,
    )


def _run_render_session(
    *,
    env: "Environment" | None = None,
    build_env: Callable[["Pygame_Renderer"], "Environment"] | None = None,
    policy_mode: str = "preview",
    layout: Any | None = None,
    tile_size: int | None = None,
    model_name: str | None = None,
    model_key: str | None = None,
    base_url: str | None = None,
    llm_policy_builder: Callable[["Environment", Entity, str], "Agent_Policy"] | None = None,
    sidebar_width: int | None = None,
    sidebar_agent_id: int = 0,
    on_policy_selection: Callable[["Environment", Any, int, "Action_Selection", dict], None] | None = None,
    keep_logs: bool = True,
    log_path: str | None = None,
    log_root: str | None = None,
    record_title: str | None = None,
    autoplay: bool = True,
    step_delay: float = 0.25,
    max_steps: int | None = None,
    initial_notes: list[str] | None = None,
) -> str | None:
    """Build an env, optionally attach LLM policies, and run the shared live renderer."""
    from word_play.core.components import Agent_Policy
    from word_play.presets.renderers.renderer import (
        Environment_Layout_Adapter,
        Pygame_Renderer,
        apply_agent_sidebar,
        apply_policy_selection_sidebar,
    )

    if policy_mode == "llm":
        if model_name is None or model_key is None or base_url is None:
            raise ValueError("LLM mode requires model_name, model_key, and base_url.")
        if llm_policy_builder is None:
            raise ValueError("LLM mode requires an llm_policy_builder.")

        
    if env is None and build_env is None:
        raise ValueError("_run_render_session requires either env or build_env.")

    resolved_tile_size = tile_size or 32
    renderer = Pygame_Renderer(layout=layout or Environment_Layout_Adapter(), tile_size=resolved_tile_size)
    env = env if env is not None else build_env(renderer)
    if hasattr(env, "renderer_impl"):
        env.renderer_impl = renderer

    if tile_size is None:
        width = getattr(env, "width", None)
        height = getattr(env, "height", None)
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            longest_side = max(width, height)
            renderer.tile_size = max(32, min(72, int(840 / longest_side)))
        else:
            renderer.tile_size = 56

    resolved_max_steps = max_steps
    if resolved_max_steps is None:
        resolved_max_steps = getattr(env, "episode_length", 200)

    env_label = (getattr(env, "description", None) or env.__class__.__name__).strip()
    resolved_record_title = record_title
    if resolved_record_title is None:
        resolved_record_title = f"{env_label} LLM Example" if policy_mode == "llm" else f"{env_label} Example"

    resolved_initial_notes = initial_notes
    if resolved_initial_notes is None:
        resolved_initial_notes = [
            f"{env_label} booted." if policy_mode != "llm" else f"{env_label} LLM run booted."
        ]

    if policy_mode == "llm":
        from word_play.presets.models import OpenRouter_Model, LLM_MODEL_REGISTRY
        LLM_MODEL_REGISTRY[model_key] = OpenRouter_Model(
            model_name=model_name,
            generation_params={"temperature": 0.2},
        )

        if sidebar_width is not None:
            env.hud_sidebar_width = sidebar_width
        for agent in env.agents:
            components = {
                ctype: component
                for ctype, component in agent.components.items()
                if not isinstance(component, Agent_Policy)
            }
            policy = llm_policy_builder(env, agent, model_key)
            policy.entity = agent
            components[type(policy)] = policy
            agent.components = components
            agent.is_agent = True
        env._init_agent_list()
        env._init_agent_idx_dict()

        if env.agents and 0 <= sidebar_agent_id < len(env.agents):
            apply_agent_sidebar(env, observation=env.observe(sidebar_agent_id))

    run_policy_live_view(
        renderer,
        env=env,
        on_policy_selection=(
            on_policy_selection
            if on_policy_selection is not None
            else (
                None
                if policy_mode != "llm"
                else lambda env, observation, agent_id, selection, info: apply_policy_selection_sidebar(
                    env,
                    observation=observation,
                    selection=selection,
                    info=info,
                )
            )
        ),
        keep_logs=keep_logs or policy_mode == "llm",
        log_path=log_path,
        log_root=log_root,
        record_title=resolved_record_title,
        step_delay=step_delay,
        max_steps=resolved_max_steps,
        initial_notes=resolved_initial_notes,
    )
    return renderer.last_record_path


def Run_Render(
    *,
    description: str,
    default_policy: str,
    default_model_name: str,
    default_model_key: str,
    default_base_url: str,
    default_log_dir: str,
    env: "Environment" | None = None,
    build_env: Callable[["Pygame_Renderer"], "Environment"] | None = None,
    llm_policy_builder: Callable[["Environment", Entity, str], "Agent_Policy"] | None = None,
    sidebar_width: int | None = None,
    record_title_builder: Callable[[str], str] | None = None,
    initial_notes_builder: Callable[[str], list[str]] | None = None,
    step_delay: float = 0.28,
    llm_step_delay: float = 0.28,
    layout: Any | None = None,
    policy_choices: list[str] | None = None,
    default_tile_size: int | None = None,
) -> None:
    """Single public preset for rendered example CLIs."""
    parser = argparse.ArgumentParser(description=description)
    resolved_policy_choices = policy_choices or ["preview", "llm"]
    parser.add_argument("--policy", choices=resolved_policy_choices, default=default_policy)
    parser.add_argument("--model-name", default=default_model_name)
    parser.add_argument("--model-key", default=default_model_key)
    parser.add_argument("--base-url", default=default_base_url)
    parser.add_argument("--tile-size", type=int, default=default_tile_size)
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--delay", type=float, default=step_delay, help="Seconds between auto-stepped frames.")
    parser.add_argument("--render-delay", type=float, default=llm_step_delay, help="Alias for llm autoplay delay.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log for the live run.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log pickle.")
    parser.add_argument("--log-dir", default=default_log_dir, help="Directory for auto-named replay logs.")
    args = parser.parse_args()

    policy_mode = args.policy
    saved_log_path = _run_render_session(
        env=env,
        build_env=build_env,
        policy_mode=policy_mode,
        layout=layout,
        tile_size=args.tile_size,
        model_name=args.model_name,
        model_key=args.model_key,
        base_url=args.base_url,
        llm_policy_builder=llm_policy_builder,
        sidebar_width=sidebar_width,
        keep_logs=not args.no_logs,
        log_path=args.log_path,
        log_root=args.log_dir,
        record_title=(
            None
            if record_title_builder is None
            else record_title_builder(policy_mode)
        ),
        autoplay=not args.paused,
        step_delay=args.render_delay if policy_mode == "llm" else args.delay,
        initial_notes=(
            None
            if initial_notes_builder is None
            else initial_notes_builder(policy_mode)
        ),
    )
    if saved_log_path is not None:
        print(f"Saved replay log: {saved_log_path}")
