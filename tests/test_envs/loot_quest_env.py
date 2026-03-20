from __future__ import annotations

from tests import _path_setup  # noqa: F401
from word_play.core import Entity, Environment
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement import Move_Right, Position_1D
from word_play.presets.movement.simple_1d_grid import INFINITE_1D_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Do_Nothing, Inventory, Pick_Up_Item

from tests.test_envs.rpg_test_helpers import (
    Loot,
    ManualAgentPolicy,
    TinyObservation,
    action_for,
    random_action_for,
)


class LootQuestEnv(Environment):
    def __init__(self):
        rogue = Entity(
            name="Rogue",
            position=Position_1D(0),
            tags=["agent"],
            actions=list(INFINITE_1D_MOVEMENT_SYSTEM.movement_options) + [Do_Nothing()],
            components=[ManualAgentPolicy(), Inventory(collectable_tags=["loot"])],
        )
        potion = Entity(
            name="Potion Drop",
            position=Position_1D(2),
            tags=["loot"],
            components=[Loot(item_name="healing_potion")],
        )
        super().__init__(
            description="Simple loot pickup environment.",
            entities=[rogue, potion],
            movement_system=INFINITE_1D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id):
        return TinyObservation(
            self.possible_actions(self.agents[agent_id]),
            "Loot quest observation",
        )

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


def run_loot_quest_env(mode: str = "predefined", steps: int = 4, seed: int = 7) -> dict:
    import random

    random.seed(seed)
    env = LootQuestEnv()
    if mode == "predefined":
        for a_type, target in [
            (Move_Right, "Rogue"),
            (Move_Right, "Rogue"),
            (Pick_Up_Item, "Potion Drop"),
        ]:
            a = action_for(env, "Rogue", a_type, target)
            print(f"➜ [{a.actor.name}] uses [{a.action.__class__.__name__}] on [{a.target_entity.name}]")
            env.step([a])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            print(f"➜ [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError("Unsupported mode: {mode}".format(mode=mode))

    rogue = next(entity for entity in env.state.entities if entity.name == "Rogue")
    inventory = rogue.require_component(Inventory)
    position = rogue.position
    rogue_x = getattr(position, "x", None)
    if rogue_x is None:
        raise ValueError("LootQuestEnv expected Rogue to use a 1D position with an x coordinate.")
    return {
        "rogue_position": rogue_x,
        "rogue_inventory": [item.name for item in inventory.inventory],
        "remaining_entities": [entity.name for entity in env.state.entities],
    }
