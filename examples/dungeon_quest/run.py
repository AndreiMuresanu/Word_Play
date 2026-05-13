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

from examples.dungeon_quest.environment import (  # noqa: E402
    DungeonRaidEnv,
)
from word_play.core import Agent_Policy  # noqa: E402
from word_play.presets.renderers import EnvironmentLayoutAdapter, PygameRenderer  # noqa: E402

DEFAULT_LOG_DIR = PROJECT_ROOT / "experiments" / "logs" / "dungeon_quest"


def run_dungeon_quest(
    *,
    tile_size: int = 72,
    autoplay: bool = True,
    step_delay: float = 0.55,
    keep_logs: bool = True,
    log_path: str | None = None,
    log_dir: str | None = None,
) -> str | None:
    """Run the dungeon preview in the live renderer."""
    renderer = PygameRenderer(layout=EnvironmentLayoutAdapter(), tile_size=tile_size)

    def reset_factory() -> DungeonRaidEnv:
        return DungeonRaidEnv(renderer=renderer)

    def step_builder(env: DungeonRaidEnv):
        selections = []
        for agent in env.agents:
            observation = env.observe(env.agent_to_idx[agent])
            selection, _info = agent.get_component(Agent_Policy).select_action(observation)
            selections.append(selection)
        return selections

    initial_env = reset_factory()
    renderer.run_live_view(
        initial_env,
        step_builder=step_builder,
        keep_logs=keep_logs,
        log_path=log_path,
        log_root=log_dir or str(DEFAULT_LOG_DIR),
        record_title="Dungeon Quest Example",
        autoplay=autoplay,
        step_delay=step_delay,
        max_steps=initial_env.episode_length,
        reset_factory=reset_factory,
        initial_notes=["Dungeon quest booted.", "Sparse reward: only boss defeat pays out."],
    )
    return renderer.last_record_path


def main() -> None:
    """Parse CLI arguments and launch the dungeon example."""
    parser = argparse.ArgumentParser(description="Run the dungeon quest example.")
    parser.add_argument("--tile-size", type=int, default=72)
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--delay", type=float, default=0.55, help="Seconds between auto-stepped frames.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log for the live run.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log pickle.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    args = parser.parse_args()

    saved_log_path = run_dungeon_quest(
        tile_size=args.tile_size,
        autoplay=not args.paused,
        step_delay=args.delay,
        keep_logs=not args.no_logs,
        log_path=args.log_path,
        log_dir=args.log_dir,
    )
    if saved_log_path is not None:
        print(f"Saved replay log: {saved_log_path}")


if __name__ == "__main__":
    main()
