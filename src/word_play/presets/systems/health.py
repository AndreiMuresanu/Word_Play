from __future__ import annotations

from word_play.core import Component, Environment


class Health(Component):

    def __init__(self, max_health: float, starting_health: float):
        super().__init__()
        self.max_health = max_health
        self.health = starting_health

    def post_actions_step(self, env: Environment) -> None:
        # NOTE: race conditions (e.g., entity is destory only on the next step after a killing blow) due to action order
        #       are avoided since all entity step funcs are run after the actions are resolved
        # NOTE: If both agents A and B have 1 health and they both zap each other on the same turn for 1 damage. Under
        #       the current implementation, they will both die, instead of only the agent who gets zapped first dying.
        #       This is because the agents are only destroyed in post_actions_step, i.e., after all actions have executed
        if self.health <= 0:
            env.destroy_entity(self.entity)
