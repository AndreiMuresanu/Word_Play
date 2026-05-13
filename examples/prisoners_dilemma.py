from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from word_play.core import Agent_Policy, Entity
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model

from prisoners_dilemma_env import (
    Cooperate,
    Defect,
    Prisoners_Dilemma,
    Prisoners_Dilemma_Position,
    build_prisoners_dilemma_agents,
)


def build_llm_policy(model_key: str) -> LLM_Action_And_Communication_Policy:
    return LLM_Action_And_Communication_Policy(model_key=model_key)


def register_models(model_mode: str, num_agents: int = 2) -> list[str]:
    model_keys = [f"prisoners_dilemma_{model_mode}_{idx}" for idx in range(num_agents)]

    if model_mode == "human_llm":
        for key in model_keys:
            LLM_MODEL_REGISTRY.register(key, Human_Model)
        return model_keys
    if model_mode == "openrouter_small":
        model_name = "meta-llama/llama-3.2-1b-instruct"
        generation_config = {"temperature": 0.0}
    elif model_mode == "openrouter_mid":
        model_name = "meta-llama/llama-3-8b-instruct"
        generation_config = {"temperature": 0.0}
    elif model_mode == "openrouter_large":
        model_name = "openai/gpt-5.4"
        generation_config = {"temperature": 0.0}
    else:
        raise ValueError(f"Unsupported model_mode: {model_mode}")

    system_prompt = (
        "You are playing repeated Prisoner's Dilemma. "
        "Choose the action that maximizes your reward across the full repeated game. "
        'Respond only with JSON: {"action_choice_idx": <integer>}.'
    )
    for key in model_keys:
        LLM_MODEL_REGISTRY.register(
            key,
            OpenRouter_Model,
            model_name=model_name,
            system_prompt=system_prompt,
            generation_config=generation_config,
            app_name="Word Play",
        )
    return model_keys


def build_human_agents() -> list[Entity]:
    return [
        Entity(
            name="Agent A",
            position=Prisoners_Dilemma_Position(),
            actions=[Cooperate(), Defect()],
            components=[Human_Takes_Action()],
        ),
        Entity(
            name="Agent B",
            position=Prisoners_Dilemma_Position(),
            actions=[Cooperate(), Defect()],
            components=[Human_Takes_Action()],
        ),
    ]


def run_exp(
    model_mode: str = "human_action",
    reward_log_path: str | None = None,
    max_rounds: int = 40,
) -> None:
    if model_mode == "human_action":
        agents = build_human_agents()
    else:
        model_keys = register_models(model_mode)
        agents = build_prisoners_dilemma_agents(
            *[build_llm_policy(model_key) for model_key in model_keys],
        )

    env = Prisoners_Dilemma(
        description="Repeated Prisoner's Dilemma benchmark.",
        agents=agents,
        max_rounds=max_rounds,
    )

    reward_fieldnames = [
        "round",
        "joint_profile",
        "agent_a_choice",
        "agent_b_choice",
        "agent_a_reward",
        "agent_b_reward",
        "mean_reward",
        "agent_a_cumulative_reward",
        "agent_b_cumulative_reward",
        "model_mode",
    ]
    csv_file = None
    reward_writer = None
    if reward_log_path:
        parent_dir = os.path.dirname(reward_log_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        csv_file = open(reward_log_path, "w", newline="")
        reward_writer = csv.DictWriter(csv_file, fieldnames=reward_fieldnames)
        reward_writer.writeheader()
        csv_file.flush()

    reward_rows = []
    try:
        for round_idx in range(max_rounds):
            cur_round_actions = []
            for agent_id, controlled_agent in enumerate(env.agents):
                observation = env.observe(agent_id)
                action, info = controlled_agent.get_component(Agent_Policy).select_action(observation)
                print(f"[round {round_idx}] {controlled_agent.name} -> {action}")
                if info:
                    if info.get("reasoning"):
                        print(f"[round {round_idx}] reasoning:\n{info['reasoning']}")
                    if info.get("raw_response"):
                        print(f"[round {round_idx}] raw response:\n{info['raw_response']}")
                cur_round_actions.append(action)

            env.step(cur_round_actions)
            round_info = env.infos[0].get("action_info", {})
            choices = round_info.get("choices", {})
            rewards = round_info.get("rewards", {})
            cumulative_rewards = round_info.get("cumulative_rewards", {})
            print(
                f"[round {round_idx}] profile={round_info.get('joint_profile')} "
                f"choices={choices} rewards={rewards} cumulative={cumulative_rewards}"
            )

            reward_row = {
                "round": round_idx,
                "joint_profile": round_info.get("joint_profile"),
                "agent_a_choice": choices.get("Agent A"),
                "agent_b_choice": choices.get("Agent B"),
                "agent_a_reward": rewards.get("Agent A"),
                "agent_b_reward": rewards.get("Agent B"),
                "mean_reward": sum(env.last_rewards) / len(env.last_rewards),
                "agent_a_cumulative_reward": cumulative_rewards.get("Agent A"),
                "agent_b_cumulative_reward": cumulative_rewards.get("Agent B"),
                "model_mode": model_mode,
            }
            reward_rows.append(reward_row)
            if reward_writer is not None:
                reward_writer.writerow(reward_row)
                csv_file.flush()

            if all(env.truncations) or all(env.terminations):
                print(f"Episode ended at round {round_idx + 1}.")
                break
    finally:
        if csv_file is not None:
            csv_file.close()
            print(f"Saved reward log to {reward_log_path}")


if __name__ == "__main__":
    run_exp(
        model_mode=sys.argv[1] if len(sys.argv) > 1 else "human_action",
        reward_log_path=sys.argv[2] if len(sys.argv) > 2 else None,
        max_rounds=int(sys.argv[3]) if len(sys.argv) > 3 else 40,
    )
