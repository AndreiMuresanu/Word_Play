from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from examples.overcooked.environment import (  # noqa: E402
    KitchenLayoutAdapter,
    OvercookedKitchenEnv,
    SinglePlayerOvercookedEnv,
    select_policy_actions,
)
from word_play.presets.renderers import PygameRenderer  # noqa: E402

DEFAULT_LOG_DIR = PROJECT_ROOT / "experiments" / "logs" / "overcooked"


def run_overcooked_example(
    *,
    tile_size: int = 56,
    autoplay: bool = True,
    step_delay: float = 0.28,
    keep_logs: bool = True,
    log_path: str | None = None,
    log_dir: str | None = None,
    single_player: bool = False,
) -> str | None:
    """Run the overcooked preview in the live renderer."""
    renderer = PygameRenderer(layout=KitchenLayoutAdapter(), tile_size=tile_size)
    env_type = SinglePlayerOvercookedEnv if single_player else OvercookedKitchenEnv

    def reset_factory() -> OvercookedKitchenEnv:
        return env_type(renderer=renderer)

    def step_builder(env: OvercookedKitchenEnv):
        return select_policy_actions(env)

    initial_env = reset_factory()
    renderer.run_live_view(
        initial_env,
        step_builder=step_builder,
        keep_logs=keep_logs,
        log_path=log_path,
        log_root=log_dir or str(DEFAULT_LOG_DIR),
        record_title="Overcooked Example",
        autoplay=autoplay,
        step_delay=step_delay,
        max_steps=initial_env.episode_length,
        reset_factory=reset_factory,
        initial_notes=[
            "Overcooked kitchen booted.",
            "Cook, plate, and deliver the queued garden skillets before closing.",
        ],
    )
    return renderer.last_record_path

def main() -> None:
    """Parse CLI arguments and launch the overcooked example."""
    parser = argparse.ArgumentParser(description="Run the overcooked example.")
    parser.add_argument("--tile-size", type=int, default=56)
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--delay", type=float, default=0.28, help="Seconds between auto-stepped frames.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log for the live run.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log pickle.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    parser.add_argument("--single-player", action="store_true", help="Run the one-chef kitchen variant.")
    args = parser.parse_args()

    saved_log_path = run_overcooked_example(
        tile_size=args.tile_size,
        autoplay=not args.paused,
        step_delay=args.delay,
        keep_logs=not args.no_logs,
        log_path=args.log_path,
        log_dir=args.log_dir,
        single_player=args.single_player,
    )
    if saved_log_path is not None:
        print(f"Saved replay log: {saved_log_path}")


if __name__ == "__main__":
    main()
