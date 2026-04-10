from word_play.core import Agent_Policy
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model

import csv
import os
import sys
from line_tracking_1d_env import Line_Tracking_1D, build_line_tracking_agent


def register_model(model_mode: str) -> str:
    model_key = "line_tracking_model"
    if model_mode == "human_llm":
        LLM_MODEL_REGISTRY.register(model_key, Human_Model)
        return model_key
    if model_mode == "openrouter_small":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="meta-llama/llama-3.2-1b-instruct",
            system_prompt=(
                'Your goal is to keep the agent aligned with the moving target. '
                'Use the target side and drift direction to decide whether to move left, stay still, or move right. '
                'Respond only with JSON: {"action_choice_idx": <integer>}.'
            ),
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key
    if model_mode == "openrouter_mid":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="meta-llama/llama-3-8b-instruct",
            system_prompt="You are controlling a line tracking system. Choose the action that keeps the agent aligned with the moving target and follow the output format exactly.",
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key
    if model_mode == "openrouter_large":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="openai/gpt-5.4",
            system_prompt="You are controlling a line tracking system. Choose the action that keeps the agent aligned with the moving target and follow the output format exactly.",
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key
    raise ValueError(f"Unsupported model_mode: {model_mode}")


def run_exp(model_mode: str = "human_action", exp_steps: int = 100, reward_log_path: str | None = None):
    model_key = register_model(model_mode) if model_mode != "human_action" else None
    agent = build_line_tracking_agent(
        "Tracker",
        LLM_Action_And_Communication_Policy(model_key=model_key)
        if model_mode != "human_action"
        else Human_Takes_Action(),
    )
    env = Line_Tracking_1D(
        description="1D line tracking benchmark.",
        entities=[agent],
        line_min=-10,
        line_max=10,
        lose_distance=8,
        max_steps=exp_steps,
    )

    reward_rows = []
    for step in range(exp_steps):
        cur_step_actions = []
        step_infos = []
        for agent_id, controlled_agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = controlled_agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {controlled_agent.name} -> {action}")
            if info:
                if info.get("reasoning"):
                    print(f"[step {step}] reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[step {step}] raw response:\n{info['raw_response']}")
            cur_step_actions.append(action)
            step_infos.append((controlled_agent, action, info))

        env.step(cur_step_actions)
        reward_rows.append(
            {
                "step": step,
                "reward": env.last_rewards[0],
                "terminated": env.terminations[0],
                "truncated": env.truncations[0],
                "agent_position": env.agents[0].position.x,
                "target_position": env.target_position,
                "target_drift_direction": env.target_drift_direction,
                "action": str(cur_step_actions[0]),
                "model_mode": model_mode,
            }
        )
        if env.terminations[0]:
            print(f"Episode ended at step {step + 1}.")
            break
        if env.truncations[0]:
            print(f"Episode reached the step limit at step {step + 1}.")
            break

    if reward_log_path:
        parent_dir = os.path.dirname(reward_log_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(reward_log_path, "w", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "step",
                    "reward",
                    "terminated",
                    "truncated",
                    "agent_position",
                    "target_position",
                    "target_drift_direction",
                    "action",
                    "model_mode",
                ],
            )
            writer.writeheader()
            writer.writerows(reward_rows)
        print(f"Saved reward log to {reward_log_path}")


if __name__ == "__main__":
    run_exp(
        sys.argv[1] if len(sys.argv) > 1 else "human_action",
        int(sys.argv[3]) if len(sys.argv) > 3 else 100,
        sys.argv[2] if len(sys.argv) > 2 else None,
    )
