from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from typing import TYPE_CHECKING, Any, Callable

from word_play.core.components import Agent_Policy, Non_Agent_Policy

if TYPE_CHECKING:
    from word_play.core import Action_Selection, Environment, Observation


Policy_Selection_Callback = Callable[["Environment", Any, int, "Action_Selection", dict], None]


def select_action(env: "Environment", agent_id: int, observation: "Observation") -> tuple["Action_Selection", dict]:
    agent = env.agents[agent_id]
    policy = agent.get_component(Agent_Policy)

    if policy is not None:
        selection, info = policy.select_action(observation)
        return selection, dict(info or {})

    policy = agent.get_component(Non_Agent_Policy)
    selection = policy.select_action(possible_actions=env.possible_actions(agent), env=env)
    return selection, {}


def build_policy_step_actions(
    env: "Environment",
    *,
    batched: bool = True,
    max_workers: int | None = None,
    on_selection: Policy_Selection_Callback | None = None,
) -> list["Action_Selection"]:
    """Build one action per agent.

    In batched mode, observations are built first, then LLM policies are
    queried concurrently. The environment is only stepped by the caller after
    all actions are returned.
    """
    observations = [env.observe(agent_id) for agent_id in range(len(env.agents))]
    agent_ids = list(range(len(env.agents)))

    if batched:
        worker_count = max_workers or len(agent_ids)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(select_action, repeat(env), agent_ids, observations))
    else:
        results = [select_action(env, agent_id, observations[agent_id]) for agent_id in agent_ids]

    selections: list[Action_Selection] = []
    for agent_id, (selection, info) in enumerate(results):
        if on_selection is not None:
            on_selection(env, observations[agent_id], agent_id, selection, info)
        selections.append(selection)

    return selections
