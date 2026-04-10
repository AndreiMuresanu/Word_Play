from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from word_play.core import Agent_Policy, Entity
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from private_sum_coordination_env import (
    Play_Signal,
    Private_Sum_Coordination,
    Shared_Room_Position,
    build_private_sum_agents,
)
from word_play.presets.models import Human_Model, Lazy_Model_Handle, LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import Human_Communication_Policy
from word_play.presets.systems.communication.core import Communication_Policy


def build_llm_policy(model_key: str) -> LLM_Action_And_Communication_Policy:
    return LLM_Action_And_Communication_Policy(model_key=model_key)


def register_models(model_mode: str, num_agents: int) -> list[str]:
    model_keys = [f"private_sum_model_{idx}" for idx in range(num_agents)]

    if model_mode == "human_llm":
        shared_model = Lazy_Model_Handle(lambda: Human_Model())
    elif model_mode == "openrouter_small":
        shared_model = Lazy_Model_Handle(
            lambda: OpenRouter_Model(
                model_name="meta-llama/llama-3.2-1b-instruct",
                system_prompt=(
                    "You are a cooperative game agent. "
                    "Follow the requested output format exactly. "
                    "If asked for action selection, return only the required JSON. "
                    "If asked to send a chat message, send one short plain-text message."
                ),
                generation_params={"temperature": 0.2},
                app_name="Word Play",
            )
        )
    elif model_mode == "openrouter_mid":
        shared_model = Lazy_Model_Handle(
            lambda: OpenRouter_Model(
                model_name="meta-llama/llama-3-8b-instruct",
                system_prompt=(
                    "You are a cooperative game agent. "
                    "Follow the requested output format exactly. "
                    "If asked for action selection, return only the required JSON. "
                    "If asked to send a chat message, send one short plain-text message."
                ),
                generation_params={"temperature": 0.2},
                app_name="Word Play",
            )
        )
    elif model_mode == "openrouter_large":
        shared_model = Lazy_Model_Handle(
            lambda: OpenRouter_Model(
                model_name="openai/gpt-5.4",
                system_prompt=(
                    "You are a cooperative game agent. "
                    "Follow the requested output format exactly. "
                    "If asked for action selection, return only the required JSON. "
                    "If asked to send a chat message, send one short plain-text message."
                ),
                generation_params={"temperature": 0.1},
                app_name="Word Play",
            )
        )
    else:
        raise ValueError(f"Unsupported model_mode: {model_mode}")

    for key in model_keys:
        LLM_MODEL_REGISTRY[key] = shared_model
    return model_keys


def build_human_agents(num_agents: int, signal_modulus: int) -> list[Entity]:
    agents = []
    for idx in range(num_agents):
        if idx < 26:
            name = f"Agent {chr(ord('A') + idx)}"
        else:
            name = f"Agent {idx + 1}"
        agents.append(
            Entity(
                name=name,
                position=Shared_Room_Position(),
                actions=[Play_Signal(signal_value) for signal_value in range(signal_modulus)],
                components=[Human_Takes_Action(), Human_Communication_Policy()],
            )
        )
    return agents


def run_private_conversation_step(participants: list[Entity], env: Private_Sum_Coordination, step_idx: int) -> None:
    print(f"\n=== Step {step_idx} Private Messages ===")
    for participant in participants:
        participant.get_component(Communication_Policy).start_conversation(
            participants,
            env,
            info=(
                "Coordinate this step using private messages only. "
                "Share information that helps compute the team signal."
            ),
        )

    for speaker in participants:
        speaker_policy = speaker.get_component(Communication_Policy)
        speaker_signal = env.private_signal_for(speaker.name)
        for recipient in participants:
            if recipient is speaker:
                continue
            message = speaker_policy.send_message(
                [recipient],
                env,
                info=(
                    f"Current step: {step_idx}. "
                    f"Your private signal is {speaker_signal}. "
                    "Privately communicate what is needed for coordination."
                ),
            )
            print(f"{speaker.name} -> {recipient.name}: {message}")
            recipient.get_component(Communication_Policy).receive_message(message, speaker, env)

    for participant in participants:
        participant.get_component(Communication_Policy).end_conversation(participants, env)


def run_exp(
    model_mode: str = "human_action",
    num_agents: int = 3,
    max_steps: int = 40,
    signal_modulus: int = 5,
):
    if model_mode == "human_action":
        agents = build_human_agents(num_agents=num_agents, signal_modulus=signal_modulus)
    else:
        model_keys = register_models(model_mode, num_agents=num_agents)
        agents = build_private_sum_agents(
            *[build_llm_policy(model_key) for model_key in model_keys],
            signal_modulus=signal_modulus,
        )

    env = Private_Sum_Coordination(
        description="Per-step private-signal coordination benchmark.",
        agents=agents,
        signal_modulus=signal_modulus,
        max_steps=max_steps,
    )

    participants = env.agents
    for step_idx in range(max_steps):
        if all(participant.has_component(Communication_Policy) for participant in participants):
            run_private_conversation_step(participants, env, step_idx)

        cur_step_actions = []
        for agent_id, controlled_agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = controlled_agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step_idx}] {controlled_agent.name} -> {action}")
            if info:
                if info.get("reasoning"):
                    print(f"[step {step_idx}] reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[step {step_idx}] raw response:\n{info['raw_response']}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)

        step_info = env.infos[0].get("action_info", {})
        print(
            f"[step {step_idx}] status={step_info.get('team_status')} "
            f"expected={step_info.get('expected_signal')} choices={step_info.get('choices')} "
            f"reward={env.last_rewards[0]}"
        )

        if all(env.truncations) or all(env.terminations):
            print(f"Episode ended at step {step_idx + 1}.")
            break


if __name__ == "__main__":
    run_exp(
        model_mode=sys.argv[1] if len(sys.argv) > 1 else "human_action",
        num_agents=int(sys.argv[2]) if len(sys.argv) > 2 else 3,
        max_steps=int(sys.argv[3]) if len(sys.argv) > 3 else 40,
        signal_modulus=int(sys.argv[4]) if len(sys.argv) > 4 else 5,
    )
