from __future__ import annotations

from tests import _path_setup  # noqa: F401
from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement import Single_Point_Position
from word_play.presets.movement.single_point import SINGLE_POINT_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Do_Nothing

from tests.test_envs.rpg_test_helpers import (
    Heal,
    LocalHealth,
    ManualAgentPolicy,
    TinyObservation,
    action_for,
    random_action_for,
)


class HealingShrineEnv(Environment):
    def __init__(self):
        cleric = Entity(
            name="Cleric",
            position=Single_Point_Position(),
            tags=["agent"],
            actions=[Heal(amount=2), Do_Nothing()],
            components=[ManualAgentPolicy()],
        )
        fighter = Entity(
            name="Fighter",
            position=Single_Point_Position(),
            tags=["ally"],
            components=[LocalHealth(current_health=2, max_health=3)],
        )
        super().__init__(
            description="Simple healing environment.",
            entities=[cleric, fighter],
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id):
        return TinyObservation(
            self.possible_actions(self.agents[agent_id]),
            "Healing shrine observation",
        )

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


def run_healing_shrine_env(mode: str = "predefined", steps: int = 3, seed: int = 7) -> dict:
    import random

    random.seed(seed)
    env = HealingShrineEnv()
    if mode == "predefined":
        action = action_for(env, "Cleric", Heal, "Fighter")
        print(f"➜ [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
        env.step([action])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            print(f"➜ [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError("Unsupported mode: {mode}".format(mode=mode))

    fighter = next(entity for entity in env.state.entities if entity.name == "Fighter")
    return {
        "fighter_health": fighter.require_component(LocalHealth).current_health,
    }
