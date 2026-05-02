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
        game_name="Prisoner's Dilemma",
        action_names=["Cooperate", "Defect"],
        payoff_matrix=[
            [(3.0, 3.0), (0.0, 5.0)],
            [(5.0, 0.0), (1.0, 1.0)],
        ],
        objective_text="\n".join(
            [
                "OBJECTIVE: Prisoner's Dilemma",
                "  You and your opponent each simultaneously choose to Cooperate or Defect.",
                "  Mutual cooperation yields 3 points each.",
                "  If one defects and the other cooperates, the defector gets 5 and the cooperator gets 0.",
                "  Mutual defection yields 1 point each.",
                "  Maximise your cumulative reward over all steps.",
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

# make one example that is not using this payoff matrix template
# 3x3 room of 5 agents, voting box in center, it runs prisoner dilemma, track reward, communication enabled
# add payoff matrix component to the preset