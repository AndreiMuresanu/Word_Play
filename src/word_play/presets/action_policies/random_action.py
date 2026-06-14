from __future__ import annotations

import random

from word_play.core import Agent_Policy, Observation
from word_play.core.actions import Action_Selection


class Random_Action_Policy(Agent_Policy):
    """Select uniformly from the available action selections."""

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        valid_actions = [
            action_selection for action_selection in observation.possible_actions if action_selection.is_valid()
        ]

        if not valid_actions:
            raise RuntimeError("Random_Action_Policy requires at least one valid action selection.")

        return random.choice(valid_actions), {"selection_mode": "uniform_random"}
