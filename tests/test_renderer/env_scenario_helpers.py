from __future__ import annotations

import random
from dataclasses import dataclass

from word_play.core import Action, Action_Selection, Agent_Policy, Entity, Environment, Observation
from word_play.presets.systems import Health

TEST_VERBOSITY = 0


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


def print_health_snapshot(env: Environment) -> None:
    if TEST_VERBOSITY < 1:
        return

    health_lines = []
    for entity in env.state.entities:
        health = entity.get_component(Health)
        if health is not None:
            health_lines.append(f"{entity.name}={health.health}/{health.max_health}")

    if health_lines:
        trace(f"  Health: {', '.join(health_lines)}")


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


def normalized_summary(env: Environment) -> dict:
    summary = summarize_env(env)
    summary["entities"] = sorted(summary["entities"], key=lambda entity: entity["name"])
    return summary
