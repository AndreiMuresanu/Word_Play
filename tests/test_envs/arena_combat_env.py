from __future__ import annotations

from tests import _path_setup  # noqa: F401
from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement import Single_Point_Position
from word_play.presets.movement.single_point import SINGLE_POINT_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Attack, Do_Nothing, Health

from tests.test_envs.rpg_test_helpers import ManualAgentPolicy, TinyObservation, action_for, random_action_for


class ArenaCombatEnv(Environment):
    def __init__(self):
        hero = Entity(
            name="Agent A",
            position=Single_Point_Position(),
            tags=["agent"],
            actions=[Attack(name="Attack", damage_amount=1), Do_Nothing()],
            components=[ManualAgentPolicy()],
        )
        target_b = Entity(
            name="Agent B",
            position=Single_Point_Position(),
            tags=["target"],
            components=[Health(max_health=3, starting_health=3)],
        )
        target_c = Entity(
            name="Agent C",
            position=Single_Point_Position(),
            tags=["target"],
            components=[Health(max_health=5, starting_health=5)],
        )
        super().__init__(
            description="Simple arena combat environment.",
            entities=[hero, target_b, target_c],
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id):
        return TinyObservation(
            self.possible_actions(self.agents[agent_id]),
            "Arena combat observation",
        )

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        dead_entities = []
        for entity in self.state.entities:
            health = entity.get_component(Health)
            if health is not None and health.health <= 0:
                dead_entities.append(entity)
        for entity in dead_entities:
            self.destroy_entity(entity)

    def _reset(self, seed=None):
        pass


def run_arena_combat_env(mode: str = "predefined", steps: int = 6, seed: int = 7) -> dict:
    import random

    random.seed(seed)
    env = ArenaCombatEnv()
    if mode == "predefined":
        sequence = [
            ("Agent A", Attack, "Agent B"),
            ("Agent A", Attack, "Agent B"),
            ("Agent A", Attack, "Agent B"),
            ("Agent A", Attack, "Agent C"),
            ("Agent A", Attack, "Agent C"),
            ("Agent A", Attack, "Agent C"),
        ]
        for actor_name, action_type, target_name in sequence:
            action = action_for(env, actor_name, action_type, target_name)
            print(f"➜ [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            print(f"➜ [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError("Unsupported mode: {mode}".format(mode=mode))

    agent_c = next((entity for entity in env.state.entities if entity.name == "Agent C"), None)
    return {
        "remaining_entities": [entity.name for entity in env.state.entities],
        "agent_c_health": None if agent_c is None else agent_c.require_component(Health).health,
    }
