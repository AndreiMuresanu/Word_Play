from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "capture_environment_frame": ".pygame_renderer.interactive_env",
    "default_experiment_log_path": ".pygame_renderer.interactive_env",
    "ExperimentRecorder": ".pygame_renderer.interactive_env",
    "load_recording_payload": ".pygame_renderer.interactive_env",
    "newest_experiment_log_path": ".pygame_renderer.interactive_env",
    "record_step": ".pygame_renderer.interactive_env",
    "Grid_Layout_Adapter": ".layout",
    "Position_Layout_Adapter": ".layout",
    "SinglePointLayout": ".layout",
    "default_replay_renderer": ".pygame_renderer.replay_and_live",
    "newest_replay_log_path": ".pygame_renderer.replay_and_live",
    "Pygame_Renderer": ".pygame_renderer.renderer",
    "replay": ".pygame_renderer.replay_and_live",
    "ReplayFrameEnvironment": ".pygame_renderer.replay_and_live",
    "replay_frames": ".pygame_renderer.replay_and_live",
    "replay_log_path": ".pygame_renderer.replay_and_live",
    "Renderable": ".pygame_renderer.renderable",
    "Renderer": "word_play.core",
    "render_environment": ".pygame_renderer.draw",
    "init_pygame_if_needed": ".pygame_renderer.runtime",
}


__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORT_MODULES[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
