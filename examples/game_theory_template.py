from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
GAMES_DIR = SCRIPT_DIR / "payoff_matrix_games"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(GAMES_DIR) not in sys.path:
    sys.path.insert(0, str(GAMES_DIR))


def available_games() -> list[str]:
    return sorted(
        path.stem
        for path in GAMES_DIR.glob("*.py")
        if path.stem not in {"common", "__init__", "model_params"}
    )


def load_game_module(game_name: str):
    module_path = GAMES_DIR / f"{game_name}.py"
    if not module_path.exists():
        raise ValueError(f"Unknown payoff-matrix game '{game_name}'. Available: {available_games()}")

    module_spec = importlib.util.spec_from_file_location(
        f"payoff_matrix_games.{game_name}",
        module_path,
    )
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"Could not load game module from {module_path}")

    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a payoff-matrix game example.",
    )
    parser.add_argument(
        "model_mode",
        nargs="?",
        default="human_action",
        choices=["human_action", "human_llm", "openrouter_small", "openrouter_mid", "openrouter_large"],
    )
    parser.add_argument(
        "game_name",
        nargs="?",
        default="prisoners_dilemma",
        choices=available_games(),
    )
    parser.add_argument("--max_steps", type=int, default=20)
    parser.add_argument("--max_rounds", type=int, dest="max_steps_legacy", default=None)
    parser.add_argument("--log", dest="reward_log_path", default=None)
    parser.add_argument("--reward_log", dest="reward_log_path", default=None)
    return parser.parse_args()


def run_exp(
    model_mode: str = "human_action",
    game_name: str = "prisoners_dilemma",
    max_steps: int = 20,
    log_path: str | None = None,
) -> None:
    game_module = load_game_module(game_name)
    game_module.run_exp(
        model_mode=model_mode,
        max_steps=max_steps,
        log_path=log_path,
    )


if __name__ == "__main__":
    args = parse_args()
    run_exp(
        model_mode=args.model_mode,
        game_name=args.game_name,
        max_steps=args.max_steps if args.max_steps_legacy is None else args.max_steps_legacy,
        log_path=args.reward_log_path,
    )
