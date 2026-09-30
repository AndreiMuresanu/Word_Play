from __future__ import annotations

from importlib import import_module
from typing import Any

from word_play.core import (
    Render_Context,
    Render_Event,
    Render_Extractor,
    Render_Scene,
    Renderer,
    Renderer_State,
)

from .layout import Grid_Layout_Adapter, Position_Layout_Adapter, SinglePointLayout
from .pygame_renderer.interactive_env import (
    ExperimentRecorder,
    capture_environment_frame,
    default_experiment_log_path,
    load_recording_payload,
    newest_experiment_log_path,
    record_step,
)
from .pygame_renderer.renderable import Renderable
from .behaviours import (
    Render_Behaviour,
    apply_behaviour,
    register_behaviour,
    resolve_behaviour,
)
from .pygame_renderer.replay_and_live import (
    ReplayFrameEnvironment,
    default_replay_renderer,
    newest_replay_log_path,
    replay,
    replay_frames,
    replay_log_path,
)


_LAZY_EXPORT_MODULES = {
    "Pygame_Renderer": ".pygame_renderer.renderer",
    "render_environment": ".pygame_renderer.draw",
    "init_pygame_if_needed": ".pygame_renderer.runtime",
    "Beautify_Config": ".pygame_renderer.beautify",
    "MOODS": ".pygame_renderer.beautify",
    "Mood": ".pygame_renderer.beautify",
    "apply_mood": ".pygame_renderer.beautify",
}


__all__ = [
    "Beautify_Config",
    "ExperimentRecorder",
    "Grid_Layout_Adapter",
    "MOODS",
    "Mood",
    "apply_mood",
    "Position_Layout_Adapter",
    "Render_Context",
    "Render_Event",
    "Render_Extractor",
    "Render_Scene",
    "Renderable",
    "Render_Behaviour",
    "register_behaviour",
    "resolve_behaviour",
    "apply_behaviour",
    "Renderer",
    "Renderer_State",
    "ReplayFrameEnvironment",
    "SinglePointLayout",
    "capture_environment_frame",
    "default_experiment_log_path",
    "default_replay_renderer",
    "init_pygame_if_needed",
    "load_recording_payload",
    "newest_experiment_log_path",
    "newest_replay_log_path",
    "Pygame_Renderer",
    "record_step",
    "render_environment",
    "replay",
    "replay_frames",
    "replay_log_path",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_LAZY_EXPORT_MODULES[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
