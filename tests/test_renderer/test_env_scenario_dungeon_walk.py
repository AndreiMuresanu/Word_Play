from __future__ import annotations

import random

import pytest

from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import random_order, randomize_agent_order
from word_play.presets.movement import Collidable, Move_Left, Move_Right, Move_Up, Position_2D
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Do_Nothing

from tests.test_renderer.env_scenario_helpers import ManualAgentPolicy, TinyObservation, action_for, normalized_summary, random_action_for, set_test_verbosity, trace


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
        return TinyObservation(self.possible_actions(self.agents[agent_id]), "Dungeon walk observation")

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


RANDOM_WALK_ENTITY_ORDERS = (random_order, randomize_agent_order)
PREDEFINED_WALK_SEQUENCE = [
    (
        ("Scout", Move_Up, "Scout"),
        ("Buddy", Move_Left, "Buddy"),
    ),
    (
        ("Scout", Move_Right, "Scout"),
        ("Buddy", Move_Up, "Buddy"),
    ),
]


def run_dungeon_walk_env(mode: str = "random", seed: int = 7, steps: int = 12, verbosity: int = 0) -> dict:
    set_test_verbosity(verbosity)
    random.seed(seed)
    results = {}
    for entity_order in RANDOM_WALK_ENTITY_ORDERS:
        env = DungeonWalkEnv(entity_order=entity_order)
        if mode == "predefined":
            for scout_step, buddy_step in PREDEFINED_WALK_SEQUENCE:
                actions = [
                    action_for(env, *scout_step),
                    action_for(env, *buddy_step),
                ]
                for action in actions:
                    trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
                env.step(actions)
        elif mode == "random":
            for _ in range(steps):
                actions = [random_action_for(env, agent) for agent in env.agents]
                for action in actions:
                    trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
                env.step(actions)
        else:
            raise ValueError(f"Unsupported mode: {mode}")
        results[entity_order.__name__] = normalized_summary(env)
    return results


@pytest.mark.scenario
def test_dungeon_walk_predefined(test_verbosity: int) -> None:
    result = run_dungeon_walk_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "random_order": {
            "description": "Small dungeon walk smoke environment.",
            "entities": [
                {"name": "Buddy", "position": "(1, 2)", "tags": ["agent"]},
                {"name": "Scout", "position": "(1, 1)", "tags": ["agent"]},
                {"name": "Wall", "position": "(1, 0)", "tags": ["wall"]},
            ],
            "agent_names": ["Scout", "Buddy"],
        },
        "randomize_agent_order": {
            "description": "Small dungeon walk smoke environment.",
            "entities": [
                {"name": "Buddy", "position": "(1, 2)", "tags": ["agent"]},
                {"name": "Scout", "position": "(1, 1)", "tags": ["agent"]},
                {"name": "Wall", "position": "(1, 0)", "tags": ["wall"]},
            ],
            "agent_names": ["Scout", "Buddy"],
        },
    }
