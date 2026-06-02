from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "capture_environment_frame": ".interactive_env",
    "default_experiment_log_path": ".interactive_env",
    "ExperimentRecorder": ".interactive_env",
    "load_recording_payload": ".interactive_env",
    "newest_experiment_log_path": ".interactive_env",
    "record_step": ".interactive_env",
    "Grid_Layout_Adapter": ".layout",
    "Position_Layout_Adapter": ".layout",
    "SinglePointLayout": ".layout",
    "default_replay_renderer": ".renderer",
    "newest_replay_log_path": ".renderer",
    "Pygame_Renderer": ".renderer",
    "replay": ".renderer",
    "ReplayFrameEnvironment": ".renderer",
    "replay_frames": ".renderer",
    "replay_log_path": ".renderer",
    "Renderable": ".renderer",
    "Renderer": ".renderer",
    "record_render_message": ".renderer",
    "render_step": ".renderer",
    "render_environment": ".draw",
    "init_pygame_if_needed": ".runtime",
}


__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORT_MODULES[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
