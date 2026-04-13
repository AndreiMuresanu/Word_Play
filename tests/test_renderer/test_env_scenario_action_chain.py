from __future__ import annotations

import pytest

from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement import Single_Point_Position
from word_play.presets.movement.single_point import SINGLE_POINT_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Action_Chain, Attack, Health

from tests.test_renderer.env_scenario_helpers import ManualAgentPolicy, TinyObservation, action_for, set_test_verbosity, trace


class ActionChainEnv(Environment):
    def __init__(self):
        striker = Entity(
            name="Striker",
            position=Single_Point_Position(),
            tags=["agent"],
            actions=[Action_Chain([Attack(name="Jab", damage_amount=1), Attack(name="Cross", damage_amount=1)])],
            components=[ManualAgentPolicy()],
        )
        dummy = Entity(
            name="Dummy",
            position=Single_Point_Position(),
            tags=["target"],
            components=[Health(max_health=4, starting_health=4)],
        )
        super().__init__(
            description="Preset action-chain environment.",
            entities=[striker, dummy],
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id):
        return TinyObservation(self.possible_actions(self.agents[agent_id]), "Action chain observation")

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


def run_action_chain_env(verbosity: int = 0) -> dict:
    set_test_verbosity(verbosity)
    env = ActionChainEnv()
    action = action_for(env, "Striker", Action_Chain, "Dummy")
    trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
    env.step([action])

    dummy = next(entity for entity in env.state.entities if entity.name == "Dummy")
    return {
        "dummy_health": dummy.get_component(Health).health,
    }


@pytest.mark.scenario
def test_action_chain_predefined(test_verbosity: int) -> None:
    result = run_action_chain_env(verbosity=test_verbosity)
    assert result == {
        "dummy_health": 2,
    }
