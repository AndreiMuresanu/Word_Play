from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from word_play.core import Agent_Policy, Entity  # noqa: E402
from word_play.presets.action_policies.llm_action_and_communication import (  # noqa: E402
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.environments.simple_1d_grid_world import Simple_1D_Grid_World  # noqa: E402
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model, register_model  # noqa: E402
from word_play.presets.movement.simple_1d_grid import Position_1D  # noqa: E402
from word_play.presets.movement.simple_2d_grid import Move_Left, Move_Right  # noqa: E402
from word_play.presets.systems.do_nothing import Do_Nothing  # noqa: E402


def goal_line_reward(explorer: Entity, goal: Entity) -> float:
    if explorer.position.x == goal.position.x:
        return 1.0
    return -0.05


def goal_reached(explorer: Entity, goal: Entity) -> bool:
    return explorer.position.x == goal.position.x


def build_goal_entity(goal_x: int = 3) -> Entity:
    return Entity(
        name="Goal",
        position=Position_1D(goal_x),
        tags=["goal"],
    )


def mark_episode_terminated(env: Simple_1D_Grid_World) -> None:
    env.terminations = [True for _ in env.terminations]


def mark_episode_truncated(env: Simple_1D_Grid_World) -> None:
    env.truncations = [True for _ in env.truncations]


GOAL_LINE_SYSTEM_PROMPT = (
    "You control Explorer in a tiny one-dimensional world. "
    "Select actions that move Explorer toward the entity named Goal. "
    "Return only the requested JSON action choice."
)


def build_goal_line_agent(
    *,
    model_key: str,
    start_x: int = 0,
    action_generation_config: dict | None = None,
) -> Entity:
    return Entity(
        name="Explorer",
        position=Position_1D(start_x),
        actions=[
            Do_Nothing(),
            Move_Left(),
            Move_Right(),
        ],
        components=[
            LLM_Action_And_Communication_Policy(
                model_key=model_key,
                system_prompt=GOAL_LINE_SYSTEM_PROMPT,
                action_generation_config=action_generation_config,
                action_max_new_tokens=512,
            )
        ],
    )


def run_exp():
    model_key = "goal_line_openrouter"
    model_name = "openai/gpt-5-mini"
    api_key_env = "OPENROUTER_API_KEY"
    start_x = 0
    goal_x = 3
    max_steps = 6
    openrouter_config = {
        "temperature": 0.0,
        "reasoning": {"effort": "minimal", "exclude": True},
    }

    if not os.getenv(api_key_env):
        raise EnvironmentError(f"Missing environment variable: {api_key_env}")

    if model_key not in LLM_MODEL_REGISTRY:
        register_model(
            model_key,
            OpenRouter_Model,
            model_name=model_name,
            generation_config=openrouter_config,
            api_key_env=api_key_env,
            base_url="https://openrouter.ai/api/v1",
            app_name="Word Play",
        )

    action_generation_config = {
        **openrouter_config,
        "response_format": {"type": "json_object"},
    }

    explorer = build_goal_line_agent(
        model_key=model_key,
        start_x=start_x,
        action_generation_config=action_generation_config,
    )
    goal = build_goal_entity(goal_x=goal_x)
    env = Simple_1D_Grid_World(
        description="One-agent action-only LLM policy demo.",
        entities=[explorer, goal],
        observation_radius=max(abs(goal_x - start_x), max_steps),
    )

    print("LLM_Action_And_Communication_Policy action-only demo")
    print(f"OpenRouter model: {model_name}")
    print("Agent actions: Do nothing, Move left, Move right")
    print("No communication actions are added.\n")

    action_history = []
    cumulative_reward = 0.0
    explorer_id = env.agent_to_idx[explorer]

    while not any(env.terminations) and not any(env.truncations):
        if goal_reached(explorer, goal):
            mark_episode_terminated(env)
            break
        if len(action_history) >= max_steps:
            mark_episode_truncated(env)
            break

        observation = env.observe(explorer_id)
        action, info = explorer.get_component(Agent_Policy).select_action(observation)
        position_before = explorer.position.x

        env.step([action])

        reward = goal_line_reward(explorer, goal)
        env.last_rewards[explorer_id] = reward
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
        if goal_reached(explorer, goal):
            mark_episode_terminated(env)
        elif len(action_history) >= max_steps:
            mark_episode_truncated(env)

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
    print(f"  reached_goal: {goal_reached(explorer, goal)}")
    print(f"  cumulative_reward: {cumulative_reward:.2f}")


if __name__ == "__main__":
    run_exp()
