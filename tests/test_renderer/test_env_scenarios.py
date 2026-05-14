from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TypeVar

import pytest

from word_play.core import Action, Action_Selection, Agent_Policy, Component, Entity, Environment, Observation
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.entity_orderings import entity_definition_order, random_order, randomize_agent_order
from word_play.presets.movement import (
    Collidable,
    Move_Down,
    Move_Left,
    Move_Right,
    Move_Up,
    Position_1D,
    Position_2D,
    Single_Point_Position,
)
from word_play.presets.movement.simple_1d_grid import INFINITE_1D_MOVEMENT_SYSTEM
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM
from word_play.presets.movement.single_point import SINGLE_POINT_MOVEMENT_SYSTEM
from word_play.presets.reward_functions import zero_reward_func
from word_play.presets.systems import Attack, Do_Nothing, Health, Inventory, Pick_Up_Item


TEST_VERBOSITY = 0
T = TypeVar("T", bound=Component)


def set_test_verbosity(level: int) -> None:
    global TEST_VERBOSITY
    TEST_VERBOSITY = max(0, level)


def trace(message: str, level: int = 1) -> None:
    if TEST_VERBOSITY >= level:
        print(message)


@dataclass(slots=True)
class TinyObservation(Observation):
    label: str

    def __str__(self) -> str:
        return self.label


def print_possible_actions(agent: Entity, possible_actions: list[Action_Selection], env: Environment) -> None:
    if TEST_VERBOSITY < 1:
        return

    trace(f"Possible actions for [{agent.name}]:")
    trace(f"  Location: {agent.position}")
    print_health_snapshot(env)
    if not possible_actions:
        trace("  - <none>")
        return

    for idx, action_selection in enumerate(possible_actions):
        trace(f"  - {idx}: {action_selection}")


def print_health_snapshot(env: Environment) -> None:
    if TEST_VERBOSITY < 1:
        return

    health_lines = []
    for entity in env.state.entities:
        health = entity.get_component(Health)
        if health is not None:
            health_lines.append(f"{entity.name}={health.health}/{health.max_health}")
            continue

        local_health = entity.get_component(LocalHealth)
        if local_health is not None:
            health_lines.append(f"{entity.name}={local_health.current_health}/{local_health.max_health}")

    if health_lines:
        trace(f"  Health: {', '.join(health_lines)}")


class ManualAgentPolicy(Agent_Policy):
    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        if not observation.possible_actions:
            raise ValueError("ManualAgentPolicy expected at least one possible action.")
        print_possible_actions(
            observation.possible_actions[0].actor,
            observation.possible_actions,
            observation.possible_actions[0].env,
        )
        return observation.possible_actions[0], {}


class Loot(Component):
    def __init__(self, item_name: str):
        super().__init__()
        self.item_name = item_name


class LocalHealth(Component):
    def __init__(self, current_health: int, max_health: int):
        super().__init__()
        self.current_health = current_health
        self.max_health = max_health


class Heal(Action):
    def __init__(self, amount: int):
        super().__init__(validation_rules=[Target_Has_Component(LocalHealth)])
        self.amount = amount

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        health = require_component(target_entity, LocalHealth)
        health.current_health = min(health.max_health, health.current_health + self.amount)
        return None

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Heal {target_entity.name}"


def action_for(env: Environment, actor_name: str, action_type: type[Action], target_name: str) -> Action_Selection:
    actor = next(entity for entity in env.state.entities if entity.name == actor_name)
    target = next(entity for entity in env.state.entities if entity.name == target_name)
    possible_actions = env.possible_actions(actor)
    print_possible_actions(actor, possible_actions, env)

    for action_selection in possible_actions:
        if isinstance(action_selection.action, action_type) and action_selection.target_entity is target:
            return action_selection

    raise ValueError(
        f"No valid action of type '{action_type.__name__}' found for actor '{actor_name}' and target '{target_name}'."
    )


def require_component(entity: Entity, component_type: type[T]) -> T:
    component = entity.get_component(component_type)
    if component is None:
        raise ValueError(f"Entity '{entity.name}' is missing required component '{component_type.__name__}'.")
    return component


def random_action_for(env: Environment, agent: Entity) -> Action_Selection:
    possible_actions = env.possible_actions(agent)
    print_possible_actions(agent, possible_actions, env)
    if not possible_actions:
        raise ValueError(f"Agent '{agent.name}' has no possible actions.")
    return random.choice(possible_actions)


def summarize_env(env: Environment) -> dict:
    return {
        "description": env.description,
        "entities": [
            {
                "name": entity.name,
                "position": str(entity.position),
                "tags": list(entity.tags),
            }
            for entity in env.state.entities
        ],
        "agent_names": [agent.name for agent in env.agents],
    }


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
        return TinyObservation(self.possible_actions(self.agents[agent_id]), "Arena combat observation")

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
        return TinyObservation(self.possible_actions(self.agents[agent_id]), "Healing shrine observation")

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


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
        return TinyObservation(self.possible_actions(self.agents[agent_id]), "Loot quest observation")

    def environment_start_of_step(self, action_selections):
        pass

    def environment_end_of_step(self, action_selections):
        pass

    def _reset(self, seed=None):
        pass


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


def _normalized_summary(env: Environment) -> dict:
    summary = summarize_env(env)
    summary["entities"] = sorted(summary["entities"], key=lambda entity: entity["name"])
    return summary


def run_arena_combat_env(mode: str = "predefined", steps: int = 6, seed: int = 7, verbosity: int = 0) -> dict:
    set_test_verbosity(verbosity)
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
            trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    agent_c = next((entity for entity in env.state.entities if entity.name == "Agent C"), None)
    return {
        "remaining_entities": [entity.name for entity in env.state.entities],
        "agent_c_health": None if agent_c is None else require_component(agent_c, Health).health,
    }


def run_healing_shrine_env(mode: str = "predefined", steps: int = 3, seed: int = 7, verbosity: int = 0) -> dict:
    set_test_verbosity(verbosity)
    random.seed(seed)
    env = HealingShrineEnv()
    if mode == "predefined":
        action = action_for(env, "Cleric", Heal, "Fighter")
        trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
        env.step([action])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    fighter = next(entity for entity in env.state.entities if entity.name == "Fighter")
    return {"fighter_health": require_component(fighter, LocalHealth).current_health}


def run_loot_quest_env(mode: str = "predefined", steps: int = 4, seed: int = 7, verbosity: int = 0) -> dict:
    set_test_verbosity(verbosity)
    random.seed(seed)
    env = LootQuestEnv()
    if mode == "predefined":
        for action_type, target in [
            (Move_Right, "Rogue"),
            (Move_Right, "Rogue"),
            (Pick_Up_Item, "Potion Drop"),
        ]:
            action = action_for(env, "Rogue", action_type, target)
            trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    elif mode == "random":
        for _ in range(steps):
            action = random_action_for(env, env.agents[0])
            trace(f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]")
            env.step([action])
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    rogue = next(entity for entity in env.state.entities if entity.name == "Rogue")
    inventory = require_component(rogue, Inventory)
    position = rogue.position
    rogue_x = getattr(position, "x", None)
    if rogue_x is None:
        raise ValueError("LootQuestEnv expected Rogue to use a 1D position with an x coordinate.")
    return {
        "rogue_position": rogue_x,
        "rogue_inventory": [item.name for item in inventory.inventory],
        "remaining_entities": [entity.name for entity in env.state.entities],
    }


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
                    trace(
                        f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]"
                    )
                env.step(actions)
        elif mode == "random":
            for _ in range(steps):
                actions = [random_action_for(env, agent) for agent in env.agents]
                for action in actions:
                    trace(
                        f"-> [{action.actor.name}] uses [{action.action.__class__.__name__}] on [{action.target_entity.name}]"
                    )
                env.step(actions)
        else:
            raise ValueError(f"Unsupported mode: {mode}")
        results[entity_order.__name__] = _normalized_summary(env)
    return results


@pytest.mark.scenario
def test_arena_combat_predefined(test_verbosity: int) -> None:
    result = run_arena_combat_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "remaining_entities": ["Agent A", "Agent C"],
        "agent_c_health": 2,
    }


@pytest.mark.scenario
def test_healing_shrine_predefined(test_verbosity: int) -> None:
    result = run_healing_shrine_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "fighter_health": 3,
    }


@pytest.mark.scenario
def test_loot_quest_predefined(test_verbosity: int) -> None:
    result = run_loot_quest_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "rogue_position": 2,
        "rogue_inventory": ["Potion Drop"],
        "remaining_entities": ["Rogue", "Potion Drop"],
    }


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
