from __future__ import annotations

import random

from word_play.core import Agent_Policy


class Random_Policy(Agent_Policy):

    def select_action(self, observation):
        return random.choice(observation.possible_actions), {}
