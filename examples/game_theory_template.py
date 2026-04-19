"""
game_theory_template.py
========================
CLI runner for repeated simultaneous-move stage games.

Usage
-----
    # Human keyboard play, Prisoner's Dilemma
    python3 examples/game_theory_template.py human_action prisoners_dilemma

    # Small LLM on OpenRouter, Pure Coordination, 15 rounds, CSV output
    python3 examples/game_theory_template.py openrouter_small pure_coordination \\
        --max_rounds 15 --reward_log results/pd_small.csv

    # Two players sharing a mid-size model, Stag Hunt
    python3 examples/game_theory_template.py openrouter_mid stag_hunt

Positional args
---------------
    model_mode   : human_action | human_llm | openrouter_small | openrouter_mid | openrouter_large
    game_name    : any key in GAME_CONFIGS (prisoners_dilemma, pure_coordination, …)

Optional args
-------------
    --max_rounds N          override default round count  (default: 20)
    --reward_log  PATH      write per-round CSV to PATH
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from word_play.core import Agent_Policy
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model

from game_theory_template_env import Game_Theory_Template_Env, build_game_theory_agents
from game_theory_template_configs import GAME_CONFIGS

try:
    from word_play.presets.systems.communication.core import Communication_Policy
    _HAS_COMM_POLICY = True
except ImportError:
    _HAS_COMM_POLICY = False


# register rmodel and system prompt here - very similar to other examples

_SYSTEM_PROMPT_TEMPLATE = (
    "You are playing the game: {game_name}. "
    "Each round you must simultaneously choose one strategy from the available actions. "
    "Respond only with JSON: {{\"action_choice_idx\": <integer>}}."
)


def register_model(model_mode: str, game_name: str) -> str:
    model_key = f"game_theory_{model_mode}"
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(game_name=game_name)

    if model_mode == "human_llm":
        LLM_MODEL_REGISTRY.register(model_key, Human_Model)
        return model_key

    if model_mode == "openrouter_small":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="meta-llama/llama-3.2-1b-instruct",
            system_prompt=system_prompt,
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key

    if model_mode == "openrouter_mid":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="meta-llama/llama-3.1-8b-instruct",
            system_prompt=system_prompt,
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key

    if model_mode == "openrouter_large":
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name="openai/gpt-5.4",
            system_prompt=system_prompt,
            generation_config={"temperature": 0.0},
            app_name="Word Play",
        )
        return model_key

    raise ValueError(f"Unsupported model_mode: '{model_mode}'")


def make_policy(model_mode: str, model_key: str | None):
    """Return a fresh policy component for one agent."""
    if model_mode == "human_action":
        return Human_Takes_Action()
    return LLM_Action_And_Communication_Policy(model_key=model_key)


def _run_communication_phase(agents, env, round_index: int) -> None:
    """
    Simple round-robin communication phase: each agent sends one message,
    all others receive it.  Only runs if every agent has a Communication_Policy.
    """
    if not _HAS_COMM_POLICY:
        return

    for agent in agents:
        if agent.get_component(Communication_Policy) is None:
            return

    for speaker in agents:
        comm = speaker.get_component(Communication_Policy)
        recipients = [a for a in agents if a is not speaker]
        comm.start_conversation(agents, env, info=f"Pre-action communication, round {round_index}.")
        message = comm.send_message(recipients, env)
        for recipient in recipients:
            recipient.get_component(Communication_Policy).receive_message(message, speaker, env)
        comm.end_conversation(agents, env)


def run_exp(
    model_mode: str = "human_action",
    game_name: str = "prisoners_dilemma",
    max_rounds: int = 20,
    reward_log_path: str | None = None,
) -> None:
    if game_name not in GAME_CONFIGS:
        raise ValueError(
            f"Unknown game '{game_name}'. Available: {list(GAME_CONFIGS)}"
        )
    spec = GAME_CONFIGS[game_name]

    model_key = register_model(model_mode, spec.game_name) if model_mode != "human_action" else None
    policies = [make_policy(model_mode, model_key) for _ in range(spec.num_players)]
    agents = build_game_theory_agents(spec, *policies)

    env = Game_Theory_Template_Env(spec=spec, agents=agents, max_rounds=max_rounds)

    print(f"\n{'='*60}")
    print(f"  Game : {spec.game_name}")
    print(f"  Mode : {model_mode}")
    print(f"  Rounds: {max_rounds}")
    print(f"  Players: {[a.name for a in env.agents]}")
    print(f"{'='*60}\n")

    reward_rows: list[dict] = []
    cumulative_rewards = [0.0] * len(env.agents)

    for round_idx in range(max_rounds):
        # pre round communication if configured
        if spec.communication_enabled:
            _run_communication_phase(env.agents, env, round_idx)

        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            cur_step_actions.append(action)

            if info and info.get("raw_response"):
                print(f"  [{agent.name}] raw: {info['raw_response'].strip()}")

        
        env.step(cur_step_actions)

        for i in range(len(env.agents)):
            cumulative_rewards[i] = env.cumulative_rewards[i]

        joint_str = ", ".join(
            f"{env.agents[i].name}={cur_step_actions[i]}"
            for i in range(len(env.agents))
        )
        rewards_str = ", ".join(
            f"{env.agents[i].name}={env.last_rewards[i]:+.2f}"
            for i in range(len(env.agents))
        )
        cum_str = ", ".join(
            f"{env.agents[i].name}={cumulative_rewards[i]:+.2f}"
            for i in range(len(env.agents))
        )
        print(f"[round {round_idx:>3}]  profile: {joint_str}")
        print(f"           rewards: {rewards_str}  |  cumulative: {cum_str}")

        row: dict = {
            "round": round_idx,
            "joint_profile": "|".join(str(a) for a in cur_step_actions),
            "mean_reward": sum(env.last_rewards) / len(env.last_rewards),
            "model_mode": model_mode,
            "game_name": game_name,
        }
        for i, agent in enumerate(env.agents):
            row[f"reward_{agent.name}"] = env.last_rewards[i]
            row[f"cumulative_{agent.name}"] = cumulative_rewards[i]
        reward_rows.append(row)

        if any(env.terminations):
            print(f"\nEpisode terminated at round {round_idx + 1}.")
            break
        if any(env.truncations):
            print(f"\nReached max rounds ({max_rounds}).")
            break

    # printing final summary here
    print(f"\n{'='*60}")
    print("  FINAL CUMULATIVE REWARDS")
    for i, agent in enumerate(env.agents):
        print(f"    {agent.name}: {cumulative_rewards[i]:+.2f}")
    print(f"{'='*60}\n")

    # this is if we want to save the results to a csv file
    if reward_log_path and reward_rows:
        parent_dir = os.path.dirname(reward_log_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        fieldnames = (
            ["round", "joint_profile"]
            + [f"reward_{a.name}" for a in env.agents]
            + ["mean_reward"]
            + [f"cumulative_{a.name}" for a in env.agents]
            + ["model_mode", "game_name"]
        )
        with open(reward_log_path, "w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(reward_rows)
        print(f"Saved reward log to {reward_log_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a repeated stage game with LLM or human agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "model_mode",
        nargs="?",
        default="human_action",
        choices=["human_action", "human_llm", "openrouter_small", "openrouter_mid", "openrouter_large"],
        help="Agent policy type.",
    )
    parser.add_argument(
        "game_name",
        nargs="?",
        default="prisoners_dilemma",
        choices=list(GAME_CONFIGS),
        help="Name of the stage game to play.",
    )
    parser.add_argument(
        "--max_rounds",
        type=int,
        default=20,
        help="Number of rounds to play (default: 20).",
    )
    parser.add_argument(
        "--reward_log",
        type=str,
        default=None,
        dest="reward_log_path",
        help="Optional path to write a per-round CSV log.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_exp(
        model_mode=args.model_mode,
        game_name=args.game_name,
        max_rounds=args.max_rounds,
        reward_log_path=args.reward_log_path,
    )