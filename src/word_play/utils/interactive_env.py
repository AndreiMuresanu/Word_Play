from __future__ import annotations

import argparse
import json
import pickle
import re
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from word_play.core import Action_Selection, Environment, Observation
from word_play.presets.renderers import Renderable
from word_play.presets.renderers.renderer import Environment_Layout_Adapter


def default_experiment_log_path(
    title: str,
    *,
    root_dir: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "experiment"
    base_dir = (
        Path(root_dir)
        if root_dir is not None
        else Path(__file__).resolve().parents[3] / "experiments" / "logs"
    )
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return base_dir / f"{slug}_{stamp}.pkl"


def newest_experiment_log_path(
    title: str,
    *,
    root_dir: str | Path | None = None,
) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "experiment"
    base_dir = (
        Path(root_dir)
        if root_dir is not None
        else Path(__file__).resolve().parents[3] / "experiments" / "logs"
    )
    return base_dir / f"{slug}_newest.pkl"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        payload = {}
        for key, item in vars(value).items():
            if key == "entity":
                continue
            payload[key] = _json_safe(item)
        if payload:
            return payload
    return str(value)

def serialize_action_selection(action_selection: Action_Selection, index: int | None = None) -> dict[str, Any]:
    payload = {
        "label": str(action_selection),
        "actor_name": action_selection.actor.name,
        "target_name": action_selection.target_entity.name,
        "action_type": action_selection.action.__class__.__name__,
        "required_kwargs": {},
    }
    if index is not None:
        payload["index"] = index
    if action_selection.required_kwargs:
        payload["required_kwargs"] = {
            name: arg.arg_description(action_selection.actor, action_selection.target_entity, action_selection.env)
            for name, arg in action_selection.required_kwargs.items()
        }
    return payload


def serialize_observation(observation: Observation) -> dict[str, Any]:
    return {
        "text": str(observation),
        "possible_actions": [
            serialize_action_selection(action_selection, index=index)
            for index, action_selection in enumerate(observation.possible_actions)
        ],
    }


def capture_environment_frame(
    env: Environment,
    selected_actions: list[Action_Selection] | None = None,
    notes: list[str] | None = None,
    frame_type: str = "state",
    draw_grid_overlay: bool | None = None,
) -> dict[str, Any]:
    hit_entity_names = [
        str(effect.get("entity_name"))
        for effect in list(getattr(env, "hit_effects", []))
        if effect.get("entity_name")
    ]
    background_tiles = []
    if hasattr(env, "background_tiles"):
        background_tiles = [_json_safe(tile) for tile in env.background_tiles()]
    else:
        adapter = Environment_Layout_Adapter()
        background_tiles = [_json_safe(tile) for tile in adapter.background(env)]

    entities = []
    min_x = max_x = min_y = max_y = 0
    bounds_initialized = False
    for entity in env.state.entities:
        renderable = entity.get_component(Renderable)
        position = entity.position
        x = getattr(position, "x", None)
        y = getattr(position, "y", None)
        if x is not None and y is not None:
            if not bounds_initialized:
                min_x = max_x = int(x)
                min_y = max_y = int(y)
                bounds_initialized = True
            else:
                min_x = min(min_x, int(x))
                max_x = max(max_x, int(x))
                min_y = min(min_y, int(y))
                max_y = max(max_y, int(y))

        entities.append(
            {
                "name": entity.name,
                "is_agent": entity.is_agent,
                "position_label": str(position),
                "x": x,
                "y": y,
                "tags": list(entity.tags),
                "renderable": None
                if renderable is None
                else {
                    "sprite_path": renderable.sprite_path,
                    "z_index": renderable.z_index,
                    "visible": renderable.visible,
                    "overlay_sprite": getattr(renderable, "overlay_sprite", None),
                    "overlay_mode": getattr(renderable, "overlay_mode", "badge"),
                    "overlay_scale": getattr(renderable, "overlay_scale", None),
                    "foreground_sprite": getattr(renderable, "foreground_sprite", None),
                    "foreground_scale": getattr(renderable, "foreground_scale", None),
                    "shadow_scale": getattr(renderable, "shadow_scale", 0.72),
                    "bob_amplitude": getattr(renderable, "bob_amplitude", 0.0),
                    "bob_speed": getattr(renderable, "bob_speed", 1.6),
                    "animation_frames": list(getattr(renderable, "animation_frames", [])),
                    "animation_fps": getattr(renderable, "animation_fps", 5.0),
                    "emissive_sprite": getattr(renderable, "emissive_sprite", None),
                    "emissive_intensity": getattr(renderable, "emissive_intensity", 84),
                },
                "overlay": None if renderable is None else getattr(renderable, "overlay_sprite", None),
                "components": {
                    component_type.__name__: _json_safe(component)
                    for component_type, component in entity.components.items()
                },
            }
        )

    if background_tiles:
        for item in background_tiles:
            x = item.get("x")
            y = item.get("y")
            if x is None or y is None:
                continue
            if not bounds_initialized:
                min_x = max_x = int(x)
                min_y = max_y = int(y)
                bounds_initialized = True
            else:
                min_x = min(min_x, int(x))
                max_x = max(max_x, int(x))
                min_y = min(min_y, int(y))
                max_y = max(max_y, int(y))

    agent_observations = []
    available_actions = {}
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        agent_observations.append(
            {
                "agent_name": agent.name,
                **serialize_observation(observation),
            }
        )
        available_actions[agent.name] = [
            serialize_action_selection(action_selection, index=index)
            for index, action_selection in enumerate(env.possible_actions(agent))
        ]

    visible_tiles = None
    env_visible_tiles = getattr(env, "visible_tiles", None)
    if callable(env_visible_tiles):
        visible_tiles = [list(tile) for tile in env_visible_tiles()]

    return {
        "frame_type": frame_type,
        "tick": getattr(env, "tick", 0),
        "description": env.description,
        "score": getattr(env, "score", None),
        "deliveries": getattr(env, "deliveries", None),
        "terminations": list(getattr(env, "terminations", [])),
        "truncations": list(getattr(env, "truncations", [])),
        "final_boss_defeated": bool(getattr(env, "final_boss_defeated", False)),
        "draw_grid_overlay": bool(getattr(env, "draw_grid_overlay", False) if draw_grid_overlay is None else draw_grid_overlay),
        "hud_header": getattr(env, "hud_header", None),
        "hud_lines": list(getattr(env, "hud_lines", [])),
        "hud_sidebar_header": getattr(env, "hud_sidebar_header", None),
        "hud_sidebar_lines": list(getattr(env, "hud_sidebar_lines", [])),
        "hud_sidebar_selected_action": list(getattr(env, "hud_sidebar_selected_action", [])),
        "hud_sidebar_actions": list(getattr(env, "hud_sidebar_actions", [])),
        "hud_sidebar_width": getattr(env, "hud_sidebar_width", None),
        "current_phase": getattr(env, "current_phase", None),
        "hide_bottom_hud": bool(getattr(env, "hide_bottom_hud", False)),
        "sight_radius": getattr(env, "sight_radius", None),
        "speech_bubble_sprite": getattr(env, "speech_bubble_sprite", None),
        "speech_bubbles": _json_safe(list(getattr(env, "speech_bubbles", []))),
        "event_log": list(getattr(env, "event_log", [])),
        "hit_entity_names": hit_entity_names,
        "hit_effects": _json_safe(list(getattr(env, "hit_effects", []))),
        "visible_tiles": visible_tiles,
        "notes": list(notes or []),
        "selected_actions": []
        if selected_actions is None
        else [serialize_action_selection(action_selection) for action_selection in selected_actions],
        "bounds": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
        },
        "background_tiles": background_tiles,
        "entities": entities,
        "agent_observations": agent_observations,
        "available_actions": available_actions,
    }


class ExperimentRecorder:
    def __init__(self, output_path: str | Path, title: str, metadata: dict[str, Any] | None = None):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.title = title
        self.metadata = metadata or {}
        self.frames: list[dict[str, Any]] = []
        self.newest_output_path = newest_experiment_log_path(title, root_dir=self.output_path.parent)

    def record(
        self,
        env: Environment,
        selected_actions: list[Action_Selection] | None = None,
        notes: list[str] | None = None,
        frame_type: str = "state",
        draw_grid_overlay: bool | None = None,
    ) -> dict[str, Any]:
        frame = capture_environment_frame(
            env,
            selected_actions=selected_actions,
            notes=notes,
            frame_type=frame_type,
            draw_grid_overlay=draw_grid_overlay,
        )
        frame["env_state_obj"] = deepcopy(env.state)
        frame["frame_index"] = len(self.frames)
        self.frames.append(frame)
        self.flush()
        return frame

    def payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "title": self.title,
            "metadata": self.metadata,
            "frame_count": len(self.frames),
            "frames": self.frames,
        }

    def flush(self) -> None:
        payload_bytes = pickle.dumps(self.payload())
        self.output_path.write_bytes(payload_bytes)
        self.newest_output_path.write_bytes(payload_bytes)


class InteractiveEnvironmentSession:
    def __init__(self, env: Environment, title: str, recorder: ExperimentRecorder | None = None):
        self.env = env
        self.title = title
        self.recorder = recorder
        self.history: list[dict[str, Any]] = []
        self._capture(frame_type="initial", notes=["Interactive session ready."])

    def _capture(
        self,
        selected_actions: list[Action_Selection] | None = None,
        notes: list[str] | None = None,
        frame_type: str = "state",
        draw_grid_overlay: bool | None = None,
    ) -> dict[str, Any]:
        frame = capture_environment_frame(
            self.env,
            selected_actions=selected_actions,
            notes=notes,
            frame_type=frame_type,
            draw_grid_overlay=draw_grid_overlay,
        )
        frame["frame_index"] = len(self.history)
        self.history.append(frame)
        if self.recorder is not None:
            self.recorder.record(
                self.env,
                selected_actions=selected_actions,
                notes=notes,
                frame_type=frame_type,
                draw_grid_overlay=draw_grid_overlay,
            )
        return frame

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": "interactive",
            "title": self.title,
            "history": self.history,
            "current_frame": self.history[-1],
            "agents": [
                {
                    "agent_name": agent.name,
                    "actions": [
                        serialize_action_selection(action_selection, index=index)
                        for index, action_selection in enumerate(self.env.possible_actions(agent))
                    ],
                }
                for agent in self.env.agents
            ],
        }

    def submit_step(self, action_requests: list[dict[str, Any]]) -> dict[str, Any]:
        requested_by_agent = {request["agent_name"]: request for request in action_requests}
        selections: list[Action_Selection] = []
        for agent in self.env.agents:
            if agent.name not in requested_by_agent:
                raise ValueError(f"Missing action for agent '{agent.name}'.")

            request = requested_by_agent[agent.name]
            possible_actions = self.env.possible_actions(agent)
            action_index = int(request["action_index"])
            if action_index < 0 or action_index >= len(possible_actions):
                raise ValueError(f"Invalid action index {action_index} for agent '{agent.name}'.")

            selection = possible_actions[action_index]
            kwargs_text = (request.get("kwargs_text") or "").strip()
            if selection.required_kwargs:
                selection.action_kwargs = selection.parse_and_validate_kwarg_list(kwargs_text)
            else:
                selection.action_kwargs = {}
            selections.append(selection)

        self.env.step(selections)
        self._capture(
            selected_actions=selections,
            notes=[f"{selection.actor.name}: {selection}" for selection in selections],
            frame_type="step",
        )
        return self.snapshot()


APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Word Play Viewer</title>
  <style>
    :root {
      --bg: #131824;
      --panel: rgba(13, 18, 29, 0.88);
      --panel-2: rgba(22, 30, 46, 0.92);
      --line: rgba(130, 164, 196, 0.22);
      --ink: #eef3ff;
      --muted: #94a6bf;
      --accent: #ffb347;
      --accent-2: #7bd7b6;
      --danger: #ff6f61;
      --shadow: 0 20px 70px rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Trebuchet MS", "Gill Sans", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255, 179, 71, 0.12), transparent 24%),
        radial-gradient(circle at top right, rgba(123, 215, 182, 0.10), transparent 28%),
        linear-gradient(180deg, #1a2030, #0d1118 55%, #090c12);
    }
    .shell {
      width: min(1400px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 18px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .hero {
      padding: 20px 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
    }
    .title {
      font-size: clamp(1.4rem, 2vw, 2.2rem);
      font-weight: 700;
      letter-spacing: 0.03em;
    }
    .subtitle {
      color: var(--muted);
      margin-top: 6px;
      font-size: 0.95rem;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    button, select, input, textarea {
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.06);
      color: var(--ink);
      font: inherit;
    }
    button {
      padding: 10px 14px;
      cursor: pointer;
      transition: transform 120ms ease, background 120ms ease;
    }
    button:hover { transform: translateY(-1px); background: rgba(255,255,255,0.10); }
    button.primary { background: linear-gradient(135deg, #ffb347, #ff8f5c); color: #1a1309; border: none; }
    button.secondary { background: linear-gradient(135deg, #89f0c8, #52b1d8); color: #09131b; border: none; }
    select, input, textarea { padding: 10px 12px; width: 100%; }
    textarea { min-height: 64px; resize: vertical; }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
      gap: 18px;
    }
    .panel { padding: 18px; }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }
    .stage-wrap {
      display: grid;
      gap: 14px;
    }
    .stage-meta {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .pill {
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
      color: var(--muted);
      font-size: 0.92rem;
    }
    .stage {
      position: relative;
      min-height: 420px;
      border-radius: 24px;
      overflow: hidden;
      background:
        linear-gradient(180deg, rgba(123, 215, 182, 0.16), transparent 26%),
        linear-gradient(180deg, rgba(255, 179, 71, 0.08), transparent 62%),
        #0b1018;
      border: 1px solid rgba(255,255,255,0.08);
      padding: 18px;
    }
    .grid {
      position: relative;
      margin: 0 auto;
      display: block;
    }
    .tile, .entity {
      position: absolute;
      border-radius: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 160ms ease, opacity 160ms ease;
    }
    .tile.floor {
      background: rgba(72, 88, 106, 0.95);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
    }
    .tile.wall {
      background: linear-gradient(145deg, rgba(131, 96, 73, 0.95), rgba(79, 57, 46, 0.98));
      box-shadow: inset 0 0 0 1px rgba(255, 227, 194, 0.12);
    }
    .entity {
      color: #081017;
      font-weight: 800;
      letter-spacing: 0.03em;
      box-shadow: 0 10px 24px rgba(0,0,0,0.22);
      border: 2px solid rgba(255,255,255,0.18);
    }
    .entity-label {
      position: absolute;
      left: 50%;
      bottom: -24px;
      transform: translateX(-50%);
      white-space: nowrap;
      color: var(--ink);
      font-size: 0.72rem;
      text-shadow: 0 2px 8px rgba(0,0,0,0.5);
    }
    .overlay-tag {
      position: absolute;
      top: -8px;
      right: -8px;
      padding: 4px 7px;
      border-radius: 999px;
      background: #101723;
      color: #fff3d1;
      font-size: 0.66rem;
      border: 1px solid rgba(255,255,255,0.08);
    }
    .timeline {
      display: grid;
      gap: 12px;
    }
    .timeline-row {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: center;
    }
    .timeline input[type="range"] { width: 100%; }
    .columns {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .text-surface {
      background: var(--panel-2);
      border-radius: 18px;
      border: 1px solid var(--line);
      padding: 14px;
      min-height: 160px;
      white-space: pre-wrap;
      line-height: 1.45;
    }
    .list {
      display: grid;
      gap: 10px;
    }
    .card {
      background: var(--panel-2);
      border-radius: 18px;
      border: 1px solid var(--line);
      padding: 14px;
    }
    .card strong { display: block; margin-bottom: 8px; }
    .actions {
      display: grid;
      gap: 12px;
    }
    .action-form {
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
    }
    .hint { color: var(--muted); font-size: 0.88rem; }
    .empty { color: var(--muted); font-style: italic; }
    @media (max-width: 1080px) {
      .layout { grid-template-columns: 1fr; }
      .columns { grid-template-columns: 1fr; }
      .hero { flex-direction: column; align-items: flex-start; }
      .controls { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <div class="title" id="title">Word Play Viewer</div>
        <div class="subtitle" id="subtitle">Loading session...</div>
      </div>
      <div class="controls">
        <button id="prevButton">Back</button>
        <button class="primary" id="playPauseButton">Play</button>
        <button id="nextButton">Next</button>
        <label class="pill">Speed
          <select id="speedSelect">
            <option value="0.5">0.5x</option>
            <option value="1" selected>1x</option>
            <option value="2">2x</option>
            <option value="4">4x</option>
          </select>
        </label>
        <label class="pill">Auto-refresh
          <select id="liveSelect">
            <option value="off">Off</option>
            <option value="on" selected>On</option>
          </select>
        </label>
      </div>
    </section>

    <div class="layout">
      <section class="panel stage-wrap">
        <div class="stage-meta" id="meta"></div>
        <div class="stage">
          <div id="grid" class="grid"></div>
        </div>
        <div class="timeline">
          <div class="timeline-row">
            <span id="frameLabel">Frame 0 / 0</span>
            <input id="timeline" type="range" min="0" max="0" value="0">
            <span id="modeLabel">Replay</span>
          </div>
        </div>
        <div class="columns">
          <div>
            <h2>Event Log</h2>
            <div id="eventLog" class="text-surface"></div>
          </div>
          <div>
            <h2>Action Summary</h2>
            <div id="actionSummary" class="text-surface"></div>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2>Observations</h2>
        <div id="observations" class="list"></div>
        <div id="interactiveSection" style="display:none; margin-top:18px;">
          <h2>Human Input</h2>
          <div id="actionForms" class="actions"></div>
          <button class="secondary" id="submitStepButton" style="margin-top:12px;">Submit Next Frame</button>
          <div class="hint" style="margin-top:8px;">Choose the next action for each agent before advancing.</div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const appState = {
      mode: "replay",
      frames: [],
      frameIndex: 0,
      playing: false,
      speed: 1,
      liveRefresh: true,
      agents: [],
    };

    const titleEl = document.getElementById("title");
    const subtitleEl = document.getElementById("subtitle");
    const metaEl = document.getElementById("meta");
    const gridEl = document.getElementById("grid");
    const frameLabelEl = document.getElementById("frameLabel");
    const modeLabelEl = document.getElementById("modeLabel");
    const timelineEl = document.getElementById("timeline");
    const eventLogEl = document.getElementById("eventLog");
    const actionSummaryEl = document.getElementById("actionSummary");
    const observationsEl = document.getElementById("observations");
    const interactiveSectionEl = document.getElementById("interactiveSection");
    const actionFormsEl = document.getElementById("actionForms");
    const playPauseButton = document.getElementById("playPauseButton");
    const prevButton = document.getElementById("prevButton");
    const nextButton = document.getElementById("nextButton");
    const submitStepButton = document.getElementById("submitStepButton");
    const speedSelect = document.getElementById("speedSelect");
    const liveSelect = document.getElementById("liveSelect");

    function cssColor(color, fallback) {
      if (!Array.isArray(color) || color.length < 3) return fallback;
      return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
    }

    function currentFrame() {
      return appState.frames[Math.max(0, Math.min(appState.frameIndex, appState.frames.length - 1))] || null;
    }

    function renderMeta(frame) {
      const pills = [
        `Tick ${frame.tick ?? 0}`,
        frame.score == null ? null : `Score ${frame.score}`,
        frame.deliveries == null ? null : `Deliveries ${frame.deliveries}`,
        `Entities ${frame.entities.length}`,
      ].filter(Boolean);
      metaEl.innerHTML = pills.map((text) => `<div class="pill">${text}</div>`).join("");
    }

    function renderGrid(frame) {
      const bounds = frame.bounds || { min_x: 0, max_x: 0, min_y: 0, max_y: 0 };
      const cols = Math.max(1, bounds.max_x - bounds.min_x + 1);
      const rows = Math.max(1, bounds.max_y - bounds.min_y + 1);
      const tileSize = Math.max(44, Math.min(68, Math.floor((window.innerWidth > 1080 ? 760 : window.innerWidth - 120) / cols)));
      gridEl.style.width = `${cols * tileSize}px`;
      gridEl.style.height = `${rows * tileSize + 28}px`;
      gridEl.innerHTML = "";

      for (const tile of frame.background_tiles || []) {
        const x = Number(tile.x) - bounds.min_x;
        const y = bounds.max_y - Number(tile.y);
        const el = document.createElement("div");
        el.className = `tile ${tile.kind || "floor"}`;
        el.style.left = `${x * tileSize}px`;
        el.style.top = `${y * tileSize}px`;
        el.style.width = `${tileSize}px`;
        el.style.height = `${tileSize}px`;
        if (tile.color) {
          el.style.background = cssColor(tile.color, el.style.background);
        }
        gridEl.appendChild(el);
      }

      const sortedEntities = [...(frame.entities || [])].sort((a, b) => {
        const aZ = a.renderable?.z_index ?? 0;
        const bZ = b.renderable?.z_index ?? 0;
        return aZ - bZ;
      });
      for (const entity of sortedEntities) {
        if (entity.x == null || entity.y == null) continue;
        if (entity.renderable && entity.renderable.visible === false) continue;
        const x = Number(entity.x) - bounds.min_x;
        const y = bounds.max_y - Number(entity.y);
        const el = document.createElement("div");
        el.className = "entity";
        el.style.left = `${x * tileSize + tileSize * 0.08}px`;
        el.style.top = `${y * tileSize + tileSize * 0.08}px`;
        el.style.width = `${tileSize * 0.84}px`;
        el.style.height = `${tileSize * 0.84}px`;
        el.style.background = cssColor(entity.renderable?.color, "#d4dbe7");
        el.textContent = entity.renderable?.glyph || entity.name.slice(0, 1).toUpperCase();
        const label = document.createElement("div");
        label.className = "entity-label";
        label.textContent = entity.name;
        el.appendChild(label);
        if (entity.overlay) {
          const tag = document.createElement("div");
          tag.className = "overlay-tag";
          tag.textContent = entity.overlay;
          el.appendChild(tag);
        }
        gridEl.appendChild(el);
      }
    }

    function renderObservations(frame) {
      const cards = (frame.agent_observations || []).map((observation) => `
        <div class="card">
          <strong>${observation.agent_name}</strong>
          <div>${observation.text || ""}</div>
        </div>
      `);
      observationsEl.innerHTML = cards.length ? cards.join("") : `<div class="empty">No agent observations recorded.</div>`;
    }

    function renderTextSurfaces(frame) {
      const events = frame.event_log?.length ? frame.event_log.map((line) => `- ${line}`).join("\\n") : "No events recorded.";
      const actions = [];
      if (frame.notes?.length) actions.push(...frame.notes);
      if (frame.selected_actions?.length) {
        actions.push(...frame.selected_actions.map((item) => `${item.actor_name} -> ${item.label}`));
      }
      eventLogEl.textContent = events;
      actionSummaryEl.textContent = actions.length ? actions.join("\\n") : "No action summary for this frame.";
    }

    function renderTimeline() {
      timelineEl.max = Math.max(0, appState.frames.length - 1);
      timelineEl.value = String(Math.min(appState.frameIndex, appState.frames.length - 1));
      frameLabelEl.textContent = `Frame ${appState.frameIndex + 1} / ${Math.max(1, appState.frames.length)}`;
    }

    function renderActionForms() {
      if (appState.mode !== "interactive") {
        interactiveSectionEl.style.display = "none";
        return;
      }
      interactiveSectionEl.style.display = "block";
      actionFormsEl.innerHTML = "";
      for (const agent of appState.agents) {
        const wrapper = document.createElement("div");
        wrapper.className = "action-form";
        const options = agent.actions.map((action) => `<option value="${action.index}">${action.index}: ${action.label}</option>`).join("");
        wrapper.innerHTML = `
          <strong>${agent.agent_name}</strong>
          <select data-agent="${agent.agent_name}" class="action-select">${options}</select>
          <textarea data-agent="${agent.agent_name}" class="kwargs-input" placeholder="Optional kwargs using ; separators when required"></textarea>
          <div class="hint">If the selected action needs kwargs, enter them here in the order shown by the environment.</div>
        `;
        actionFormsEl.appendChild(wrapper);
      }
    }

    function render() {
      const frame = currentFrame();
      if (!frame) return;
      renderMeta(frame);
      renderGrid(frame);
      renderObservations(frame);
      renderTextSurfaces(frame);
      renderTimeline();
      modeLabelEl.textContent = appState.mode === "interactive" ? "Interactive" : "Replay";
      subtitleEl.textContent = frame.description || "";
    }

    async function loadReplay() {
      const response = await fetch("/api/replay");
      const payload = await response.json();
      appState.mode = "replay";
      appState.frames = payload.frames || [];
      titleEl.textContent = payload.title || "Experiment Replay";
      if (appState.liveRefresh && appState.frameIndex >= appState.frames.length - 2) {
        appState.frameIndex = Math.max(0, appState.frames.length - 1);
      }
      renderActionForms();
      render();
    }

    async function loadInteractive() {
      const response = await fetch("/api/session");
      const payload = await response.json();
      appState.mode = "interactive";
      appState.frames = payload.history || [];
      appState.agents = payload.agents || [];
      titleEl.textContent = payload.title || "Interactive Environment";
      appState.frameIndex = Math.max(0, appState.frames.length - 1);
      renderActionForms();
      render();
    }

    async function bootstrap() {
      const response = await fetch("/api/bootstrap");
      const payload = await response.json();
      if (payload.mode === "interactive") {
        await loadInteractive();
      } else {
        await loadReplay();
      }
    }

    function playLoop() {
      if (!appState.playing) return;
      if (appState.frameIndex < appState.frames.length - 1) {
        appState.frameIndex += 1;
        render();
      }
      setTimeout(playLoop, Math.max(120, 700 / appState.speed));
    }

    playPauseButton.addEventListener("click", () => {
      appState.playing = !appState.playing;
      playPauseButton.textContent = appState.playing ? "Pause" : "Play";
      if (appState.playing) playLoop();
    });
    prevButton.addEventListener("click", () => {
      appState.frameIndex = Math.max(0, appState.frameIndex - 1);
      render();
    });
    nextButton.addEventListener("click", () => {
      appState.frameIndex = Math.min(appState.frames.length - 1, appState.frameIndex + 1);
      render();
    });
    timelineEl.addEventListener("input", (event) => {
      appState.frameIndex = Number(event.target.value);
      render();
    });
    speedSelect.addEventListener("change", (event) => {
      appState.speed = Number(event.target.value);
    });
    liveSelect.addEventListener("change", (event) => {
      appState.liveRefresh = event.target.value === "on";
    });
    submitStepButton.addEventListener("click", async () => {
      const actionRequests = [...document.querySelectorAll(".action-select")].map((selectEl) => {
        const agentName = selectEl.dataset.agent;
        const kwargsEl = document.querySelector(`.kwargs-input[data-agent="${agentName}"]`);
        return {
          agent_name: agentName,
          action_index: Number(selectEl.value),
          kwargs_text: kwargsEl ? kwargsEl.value : "",
        };
      });
      const response = await fetch("/api/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actions: actionRequests }),
      });
      const payload = await response.json();
      if (!response.ok) {
        alert(payload.error || "Failed to submit actions.");
        return;
      }
      appState.frames = payload.history || [];
      appState.agents = payload.agents || [];
      appState.frameIndex = Math.max(0, appState.frames.length - 1);
      renderActionForms();
      render();
    });

    setInterval(async () => {
      if (!appState.liveRefresh) return;
      if (appState.mode === "interactive") {
        await loadInteractive();
      } else {
        await loadReplay();
      }
    }, 1000);

    bootstrap();
  </script>
</body>
</html>
"""


class _ViewerHandler(BaseHTTPRequestHandler):
    server_version = "WordPlayViewer/1.0"

    def _json_response(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._html_response(APP_HTML)
            return
        if parsed.path == "/api/bootstrap":
            self._json_response({"mode": self.server.app_mode})
            return
        if parsed.path == "/api/replay":
            if self.server.replay_path is None:
                self._json_response({"error": "Replay mode is not active."}, status=404)
                return
            payload = json.loads(self.server.replay_path.read_text(encoding="utf-8"))
            self._json_response(payload)
            return
        if parsed.path == "/api/session":
            if self.server.session is None:
                self._json_response({"error": "Interactive mode is not active."}, status=404)
                return
            self._json_response(self.server.session.snapshot())
            return
        self._json_response({"error": "Not found."}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/step":
            self._json_response({"error": "Not found."}, status=404)
            return
        if self.server.session is None:
            self._json_response({"error": "Interactive mode is not active."}, status=404)
            return
        try:
            payload = self._read_json()
            snapshot = self.server.session.submit_step(payload.get("actions", []))
        except Exception as exc:  # noqa: BLE001
            self._json_response({"error": str(exc)}, status=400)
            return
        self._json_response(snapshot)


class _ViewerServer(ThreadingHTTPServer):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        replay_path: Path | None = None,
        session: InteractiveEnvironmentSession | None = None,
    ) -> None:
        super().__init__((host, port), _ViewerHandler)
        self.replay_path = replay_path
        self.session = session
        self.app_mode = "interactive" if session is not None else "replay"


def serve_experiment_replay(log_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    replay_path = Path(log_path)
    server = _ViewerServer(host, port, replay_path=replay_path)
    print(f"Replay viewer ready at http://{host}:{port} for {replay_path}")
    server.serve_forever()


def serve_interactive_environment(
    env_factory: Callable[[], Environment],
    *,
    title: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    recorder: ExperimentRecorder | None = None,
) -> None:
    session = InteractiveEnvironmentSession(env_factory(), title=title, recorder=recorder)
    server = _ViewerServer(host, port, session=session)
    print(f"Interactive environment ready at http://{host}:{port}")
    server.serve_forever()


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve Word Play experiment viewers.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    replay_parser = subparsers.add_parser("replay", help="Serve the replay viewer for a recorded log.")
    replay_parser.add_argument("log_path")
    replay_parser.add_argument("--host", default="127.0.0.1")
    replay_parser.add_argument("--port", type=int, default=8765)

    interactive_parser = subparsers.add_parser(
        "interactive-overcooked",
        help="Launch a browser-based human control surface for the overcooked kitchen environment.",
    )
    interactive_parser.add_argument("--host", default="127.0.0.1")
    interactive_parser.add_argument("--port", type=int, default=8765)
    interactive_parser.add_argument("--record", default=None, help="Optional path to write a replay log while you play.")

    return parser


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    if args.mode == "replay":
        serve_experiment_replay(args.log_path, host=args.host, port=args.port)
        return

    if args.mode == "interactive-overcooked":
        from word_play.presets.environments import OvercookedKitchenEnv

        recorder = None
        if args.record:
            recorder = ExperimentRecorder(args.record, title="Interactive Overcooked Session")

        def build_env() -> Environment:
            return OvercookedKitchenEnv(renderer=None)

        serve_interactive_environment(
            build_env,
            title="Interactive Overcooked Session",
            host=args.host,
            port=args.port,
            recorder=recorder,
        )


if __name__ == "__main__":
    main()
