from __future__ import annotations

from importlib import import_module
from typing import Any

from .extractors import (
    Background_Tiles_Extractor,
    Frame_Metadata_Extractor,
    Hit_Effect_Extractor,
    Speech_Bubble_Extractor,
    Visible_Renderables_Extractor,
    default_pygame_extractors,
)
from .interactive_env import (
    ExperimentRecorder,
    capture_environment_frame,
    default_experiment_log_path,
    load_recording_payload,
    newest_experiment_log_path,
    record_step,
)
from .renderable import Renderable
from .replay_and_live import (
    ReplayFrameEnvironment,
    default_replay_renderer,
    newest_replay_log_path,
    replay,
    replay_frames,
    replay_log_path,
)


_LAZY_EXPORT_MODULES = {
    "Pygame_Renderer": ".renderer",
    "init_pygame_if_needed": ".runtime",
}


__all__ = [
    "Background_Tiles_Extractor",
    "default_pygame_extractors",
    "ExperimentRecorder",
    "capture_environment_frame",
    "default_experiment_log_path",
    "Frame_Metadata_Extractor",
    "Hit_Effect_Extractor",
    "init_pygame_if_needed",
    "load_recording_payload",
    "newest_experiment_log_path",
    "newest_replay_log_path",
    "Pygame_Renderer",
    "record_step",
    "Renderable",
    "ReplayFrameEnvironment",
    "default_replay_renderer",
    "replay",
    "replay_frames",
    "replay_log_path",
    "Speech_Bubble_Extractor",
    "Visible_Renderables_Extractor",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_LAZY_EXPORT_MODULES[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
