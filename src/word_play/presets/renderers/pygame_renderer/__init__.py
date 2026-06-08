from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "ExperimentRecorder": ".interactive_env",
    "capture_environment_frame": ".interactive_env",
    "default_experiment_log_path": ".interactive_env",
    "load_recording_payload": ".interactive_env",
    "newest_experiment_log_path": ".interactive_env",
    "record_step": ".interactive_env",
    "Renderable": ".renderable",
    "Pygame_Renderer": ".renderer",
    "ReplayFrameEnvironment": ".replay_and_live",
    "default_replay_renderer": ".replay_and_live",
    "newest_replay_log_path": ".replay_and_live",
    "replay": ".replay_and_live",
    "replay_frames": ".replay_and_live",
    "replay_log_path": ".replay_and_live",
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
