"""
game_theory_template_configs.py
================================
Ready-to-use Stage_Game_Spec instances.

Adding a new game
-----------------
1. Define a `Stage_Game_Spec` here.
2. Add it to `GAME_CONFIGS` so the runner can look it up by name.
3. No env or runner code needs to change.
"""

from __future__ import annotations

from game_theory_template_env import Stage_Game_Spec

# ---------------------------------------------------------------------------
# Prisoner's Dilemma  (2-player)
# Strategy 0 = Cooperate, Strategy 1 = Defect
# Classic payoffs: T=5, R=3, P=1, S=0
# ---------------------------------------------------------------------------

prisoners_dilemma = Stage_Game_Spec(
    game_name="Prisoner's Dilemma",
    strategy_names=["Cooperate", "Defect"],
    num_players=2,
    payoff_matrix={
        (0, 0): [3.0, 3.0],   # C,C  — mutual cooperation
        (0, 1): [0.0, 5.0],   # C,D  — sucker / temptation
        (1, 0): [5.0, 0.0],   # D,C  — temptation / sucker
        (1, 1): [1.0, 1.0],   # D,D  — mutual defection
    },
    objective_text="\n".join([
        "OBJECTIVE: Prisoner's Dilemma",
        "  You and your opponent each simultaneously choose to Cooperate or Defect.",
        "  Mutual cooperation yields 3 points each.",
        "  If one defects and the other cooperates, the defector gets 5 and the cooperator gets 0.",
        "  Mutual defection yields 1 point each.",
        "  You want to maximise your cumulative reward over all rounds.",
    ]),
    communication_enabled=False,
)

# ---------------------------------------------------------------------------
# Pure Coordination  (2-player)
# Both players must choose the same strategy to earn a reward.
# Strategy 0 = Left, Strategy 1 = Right
# ---------------------------------------------------------------------------

pure_coordination = Stage_Game_Spec(
    game_name="Pure Coordination",
    strategy_names=["Left", "Right"],
    num_players=2,
    payoff_matrix={
        (0, 0): [1.0, 1.0],   # L,L  — coordinate on Left
        (0, 1): [0.0, 0.0],   # L,R  — mismatch
        (1, 0): [0.0, 0.0],   # R,L  — mismatch
        (1, 1): [1.0, 1.0],   # R,R  — coordinate on Right
    },
    objective_text="\n".join([
        "OBJECTIVE: Pure Coordination",
        "  You and your opponent each simultaneously choose Left or Right.",
        "  You both earn 1 point if you choose the same option, 0 otherwise.",
        "  There is no communication — you must infer what your opponent will do.",
    ]),
    communication_enabled=False,
)

# ---------------------------------------------------------------------------
# Stag Hunt  (2-player)
# Cooperation is risky but mutually optimal; defection is safe but suboptimal.
# Strategy 0 = Hunt Stag, Strategy 1 = Hunt Hare
# ---------------------------------------------------------------------------

stag_hunt = Stage_Game_Spec(
    game_name="Stag Hunt",
    strategy_names=["Hunt Stag", "Hunt Hare"],
    num_players=2,
    payoff_matrix={
        (0, 0): [4.0, 4.0],   # both hunt stag — best mutual outcome
        (0, 1): [0.0, 2.0],   # A hunts stag alone — fails; B hunts hare safely
        (1, 0): [2.0, 0.0],   # A hunts hare; B hunts stag alone — fails
        (1, 1): [2.0, 2.0],   # both hunt hare — safe but suboptimal
    },
    objective_text="\n".join([
        "OBJECTIVE: Stag Hunt",
        "  Hunting the stag together yields 4 points each — the best outcome.",
        "  If you hunt the stag alone (your partner hunts hare), you get 0.",
        "  Hunting the hare alone always yields 2 points regardless of your partner.",
        "  Coordinate to hunt the stag for the highest mutual reward.",
    ]),
    communication_enabled=False,
)

# ---------------------------------------------------------------------------
# Battle of the Sexes  (2-player)
# Players prefer to coordinate but each prefers a different outcome.
# Strategy 0 = Opera, Strategy 1 = Football
# ---------------------------------------------------------------------------

battle_of_the_sexes = Stage_Game_Spec(
    game_name="Battle of the Sexes",
    strategy_names=["Opera", "Football"],
    num_players=2,
    payoff_matrix={
        (0, 0): [3.0, 2.0],   # both go to Opera — A prefers this
        (0, 1): [0.0, 0.0],   # mismatch
        (1, 0): [0.0, 0.0],   # mismatch
        (1, 1): [2.0, 3.0],   # both go to Football — B prefers this
    },
    objective_text="\n".join([
        "OBJECTIVE: Battle of the Sexes",
        "  You and your opponent must coordinate on a shared activity.",
        "  Going to the Opera together gives Agent A: 3, Agent B: 2.",
        "  Going to Football together gives Agent A: 2, Agent B: 3.",
        "  A mismatch gives both players 0.",
        "  Coordination matters — but you each prefer a different equilibrium.",
    ]),
    communication_enabled=False,
)

# ---------------------------------------------------------------------------
# Coordination with Communication  (2-player pure coordination, comms on)
# Identical payoffs to pure_coordination but communication_enabled=True so
# agents can exchange messages before committing to an action.
# ---------------------------------------------------------------------------

coordination_with_comms = Stage_Game_Spec(
    game_name="Coordination with Communication",
    strategy_names=["Left", "Right"],
    num_players=2,
    payoff_matrix={
        (0, 0): [1.0, 1.0],
        (0, 1): [0.0, 0.0],
        (1, 0): [0.0, 0.0],
        (1, 1): [1.0, 1.0],
    },
    objective_text="\n".join([
        "OBJECTIVE: Coordination with Communication",
        "  You and your opponent each simultaneously choose Left or Right.",
        "  You earn 1 point if you both choose the same option, 0 otherwise.",
        "  You may communicate with your opponent before committing to an action.",
    ]),
    communication_enabled=True,
)

# ---------------------------------------------------------------------------
# Registry — add new specs here so the runner can look them up by name
# ---------------------------------------------------------------------------

GAME_CONFIGS: dict[str, Stage_Game_Spec] = {
    "prisoners_dilemma": prisoners_dilemma,
    "pure_coordination": pure_coordination,
    "stag_hunt": stag_hunt,
    "battle_of_the_sexes": battle_of_the_sexes,
    "coordination_with_comms": coordination_with_comms,
}