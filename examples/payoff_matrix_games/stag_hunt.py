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
        game_name="Stag Hunt",
        action_names=["Hunt Stag", "Hunt Hare"],
        payoff_matrix=[
            [4.0, 0.0],
            [2.0, 2.0],
        ],
        objective_text="\n".join(
            [
                "OBJECTIVE: Stag Hunt",
                "  Hunting the stag together yields 4 points each.",
                "  If you hunt the stag alone, you get 0.",
                "  Hunting the hare alone always yields 2 points.",
                "  Coordinate on Hunt Stag for the best mutual outcome.",
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
