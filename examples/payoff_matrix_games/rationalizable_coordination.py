from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import parse_common_args, run_payoff_matrix_game


def run_exp(
    model_mode: str = "human_action",
    max_steps: int = 20,
    log_path: str | None = None,
) -> None:
    run_payoff_matrix_game(
        game_name="Rationalizable Coordination",
        action_names=["A", "B"],
        payoff_matrix=[
            [4.0, 0.0],
            [0.0, 2.0],
        ],
        objective_text="\n".join(
            [
                "OBJECTIVE: Rationalizable Coordination",
                "  You and your opponent each choose A or B simultaneously.",
                "  Both choosing A gives both players 4.",
                "  Both choosing B gives both players 2.",
                "  Mismatch gives both players 0.",
                "  Coordinating on A is better than coordinating on B.",
            ]
        ),
        model_mode=model_mode,
        max_steps=max_steps,
        log_path=log_path,
    )


if __name__ == "__main__":
    args = parse_common_args()
    run_exp(
        model_mode=args.model_mode,
        max_steps=args.max_steps if args.max_steps_legacy is None else args.max_steps_legacy,
        log_path=args.log_path,
    )
