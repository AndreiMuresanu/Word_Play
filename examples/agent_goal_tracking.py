from __future__ import annotations

import os
from typing import Callable

from word_play.core import Action_Selection, Agent_Policy, Entity, Environment
from word_play.presets.action_policies.llm_action_and_communication import (
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_1d_grid_world import Simple_1D_Grid_World
from word_play.presets.env_wrappers.time_limit import TimeLimit
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model, register_model
from word_play.presets.movement.simple_1d_grid import Position_1D
from word_play.presets.movement.simple_2d_grid import Move_Left, Move_Right
from word_play.presets.systems.do_nothing import Do_Nothing


def goal_line_reward(_: list[Action_Selection], env: Environment) -> list[float]:
    goal = next(entity for entity in env.state.entities if "goal" in entity.tags)
    return [1.0 if agent.position.x == goal.position.x else -0.05 for agent in env.agents]


class Goal_Line_Env(Simple_1D_Grid_World):
    def __init__(
        self,
        description: str,
        entities: list[Entity],
        observation_radius: int = 0,
        entity_order: Callable[[list[Entity], Environment], list[int]] = entity_definition_order,
    ) -> None:
        self.goal = next((entity for entity in entities if "goal" in entity.tags), None)
        if self.goal is None:
            raise ValueError("Goal_Line_Env requires an entity tagged with 'goal'.")
        super().__init__(
            description=description,
            entities=entities,
            entity_order=entity_order,
            observation_radius=observation_radius,
            reward_func=goal_line_reward,
        )

    def goal_reached(self) -> bool:
        return any(agent.position.x == self.goal.position.x for agent in self.agents)

    def environment_end_of_step(self, action_selections: list[Action_Selection]):
        if self.goal_reached():
            self.terminations = [True for _ in self.terminations]


def run_exp():
    model_key = "goal_line_openrouter"
    model_name = "openai/gpt-5-mini"
    api_key_env_var_name = "OPENROUTER_API_KEY"
    openrouter_config = {
        "temperature": 0.0,
        "reasoning": {"effort": "minimal", "exclude": True},
    }

    if not os.getenv(api_key_env_var_name):
        raise EnvironmentError(f"Missing environment variable: {api_key_env_var_name}")

    if model_key not in LLM_MODEL_REGISTRY:
        register_model(
            model_key,
            OpenRouter_Model,
            model_name=model_name,
            generation_config=openrouter_config,
            api_key_env_var_name=api_key_env_var_name,
            base_url="https://openrouter.ai/api/v1",
            app_name="Word Play",
        )

    action_generation_config = {
        **openrouter_config,
        "response_format": {"type": "json_object"},
    }

    explorer = Entity(
        name="Explorer",
        position=Position_1D(0),
        actions=[Do_Nothing(), Move_Left(), Move_Right()],
        components=[
            LLM_Action_And_Communication_Policy(
                model_key=model_key,
                system_prompt=(
                    "You control Explorer in a tiny one-dimensional world. "
                    "Select actions that move Explorer toward the entity named Goal. "
                    "Return only the requested JSON action choice."
                ),
                action_generation_config=action_generation_config,
                action_max_new_tokens=512,
            )
        ],
    )
    goal = Entity(name="Goal", position=Position_1D(3), tags=["goal"])
    env = TimeLimit(
        Goal_Line_Env(
            description="One-agent action-only LLM policy demo.",
            entities=[explorer, goal],
            observation_radius=5,
        ),
        max_episode_steps=6,
    )

    print("LLM_Action_And_Communication_Policy action-only demo")
    print(f"OpenRouter model: {model_name}")
    print("Agent actions: Do nothing, Move left, Move right")
    print("No communication actions are added.\n")

    action_history = []
    cumulative_reward = 0.0
    explorer_id = env.agent_to_idx[explorer]

    while not any(env.terminations) and not any(env.truncations):
        observation = env.observe(explorer_id)
        action, info = explorer.get_component(Agent_Policy).select_action(observation)
        position_before = explorer.position.x

        env.step([action])

        reward = env.last_rewards[explorer_id]
        cumulative_reward += reward
        action_history.append(
            {
                "step": len(action_history),
                "position_before": position_before,
                "action": str(action),
                "position_after": explorer.position.x,
                "reward": reward,
                "raw_response": info.get("raw_response"),
            }
        )

    print("Action history:")
    for row in action_history:
        print(
            f"  step={row['step']} "
            f"x:{row['position_before']} -> {row['position_after']} "
            f"action={row['action']} "
            f"reward={row['reward']} "
            f"raw={row['raw_response']}"
        )

    print("\nSummary:")
    print(f"  final_position: {explorer.position.x}")
    print(f"  goal_position: {goal.position.x}")
    print(f"  reached_goal: {env.goal_reached()}")
    print(f"  cumulative_reward: {cumulative_reward:.2f}")


if __name__ == "__main__":
    run_exp()
