from __future__ import annotations

import random
from dataclasses import dataclass

from tests import _path_setup  # noqa: F401
from word_play.core import Action, Action_Selection, Agent_Policy, Component, Entity, Environment, Observation
from word_play.presets.action_validations import Target_Has_Component


@dataclass(slots=True)
class TinyObservation(Observation):
    label: str

    def __str__(self) -> str:
        return self.label


class ManualAgentPolicy(Agent_Policy):
    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        if not observation.possible_actions:
            raise ValueError("ManualAgentPolicy expected at least one possible action.")
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
        health = target_entity.require_component(LocalHealth)
        health.current_health = min(health.max_health, health.current_health + self.amount)
        return None

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Heal {target_entity.name}"


def action_for(env: Environment, actor_name: str, action_type: type[Action], target_name: str) -> Action_Selection:
    actor = next(entity for entity in env.state.entities if entity.name == actor_name)
    target = next(entity for entity in env.state.entities if entity.name == target_name)

    for action_selection in env.possible_actions(actor):
        if isinstance(action_selection.action, action_type) and action_selection.target_entity is target:
            return action_selection

    raise ValueError(
        f"No valid action of type '{action_type.__name__}' found for actor '{actor_name}' and target '{target_name}'."
    )


def random_action_for(env: Environment, agent: Entity) -> Action_Selection:
    possible_actions = env.possible_actions(agent)
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
