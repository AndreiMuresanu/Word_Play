from __future__ import annotations

from tests import _path_setup  # noqa: F401
from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import random_order, randomize_agent_order
from word_play.presets.movement import Collidable, Position_2D
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Do_Nothing

from tests.test_envs.rpg_test_helpers import ManualAgentPolicy, TinyObservation, random_action_for, summarize_env


class DungeonWalkEnv(Environment):
    def __init__(self, entity_order=random_order):
        scout = Entity(
            name="Scout",
            position=Position_2D(0, 0),
            tags=["agent"],
            actions=list(INFINITE_2D_MOVEMENT_SYSTEM.movement_options) + [Do_Nothing()],
            components=[ManualAgentPolicy(), Collidable(collidable_tags=["wall"])],
        )
        buddy = Entity(
            name="Buddy",
            position=Position_2D(2, 1),
            tags=["agent"],
            actions=list(INFINITE_2D_MOVEMENT_SYSTEM.movement_options) + [Do_Nothing()],
            components=[ManualAgentPolicy(), Collidable(collidable_tags=["wall"])],
        )
        wall = Entity(
            name="Wall",
            position=Position_2D(1, 0),
            tags=["wall"],
            components=[Collidable()],
        )
        super().__init__(
            description="Small dungeon walk smoke environment.",
            entities=[scout, buddy, wall],
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_order,
        )

    def observe(self, agent_id):
        return TinyObservation(
            self.possible_actions(self.agents[agent_id]),
            "Dungeon walk observation",
        )

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


RANDOM_WALK_ENTITY_ORDERS = (random_order, randomize_agent_order)


def run_dungeon_walk_env(mode: str = "random", seed: int = 7, steps: int = 12) -> dict:
    import random

    random.seed(seed)
    results = {}
    for entity_order in RANDOM_WALK_ENTITY_ORDERS:
        env = DungeonWalkEnv(entity_order=entity_order)
        if mode == "predefined":
            for _ in range(steps):
                actions = [env.possible_actions(agent)[0] for agent in env.agents]
                for a in actions:
                    print(f"➜ [{a.actor.name}] uses [{a.action.__class__.__name__}] on [{a.target_entity.name}]")
                env.step(actions)
        elif mode == "random":
            for _ in range(steps):
                actions = [random_action_for(env, agent) for agent in env.agents]
                for a in actions:
                    print(f"➜ [{a.actor.name}] uses [{a.action.__class__.__name__}] on [{a.target_entity.name}]")
                env.step(actions)
        else:
            raise ValueError("Unsupported mode: {mode}".format(mode=mode))
        results[entity_order.__name__] = summarize_env(env)
    return results
