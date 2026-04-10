from word_play.core import Agent_Policy, Entity
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import Human_Communication_Policy
from boat_race_env import Boat_Race, Boat_Position, Paddle, Wait, build_boat_race_agents

import sys


def build_llm_policy(model_key: str) -> LLM_Action_And_Communication_Policy:
    return LLM_Action_And_Communication_Policy(model_key=model_key)


def register_models(model_mode: str) -> list[str]:
    model_keys = ["boat_model_a", "boat_model_b"]

    if model_mode == "human_llm":
        for key in model_keys:
            LLM_MODEL_REGISTRY.register(key, Human_Model)
        return model_keys

    if model_mode == "openrouter_small":
        for key in model_keys:
            LLM_MODEL_REGISTRY.register(
                key,
                OpenRouter_Model,
                model_name="meta-llama/llama-3.2-1b-instruct",
                system_prompt=(
                    "You are one player in a cooperative boat race. "
                    "Your observation may contain private information that your partner does not have. "
                    "Use communication to coordinate a joint strategy. "
                    'Respond only with JSON: {"action_choice_idx": <integer>}.'
                ),
                generation_config={"temperature": 0.2},
                app_name="Word Play",
            )
        return model_keys

    if model_mode == "openrouter_big":
        for key in model_keys:
            LLM_MODEL_REGISTRY.register(
                key,
                OpenRouter_Model,
                model_name="openai/gpt-5.4",
                system_prompt=(
                    "You are one player in a cooperative boat race. "
                    "Your observation may contain private information that your partner does not have. "
                    "Use communication to coordinate a joint strategy. "
                    'Respond only with JSON: {"action_choice_idx": <integer>}.'
                ),
                generation_config={"temperature": 0.2},
                app_name="Word Play",
            )
        return model_keys

    raise ValueError(f"Unsupported model_mode: {model_mode}")


def run_conversation_round(participants, env, race_idx: int, conversation_turns: int) -> None:
    for participant in participants:
        participant.get_component(Communication_Policy).start_conversation(
            participants,
            env,
            info=(
                f"Race {race_idx + 1}: discuss a plan for this race. "
                "One of you may know something important that the other does not."
            ),
        )

    for _ in range(conversation_turns):
        for speaker in participants:
            recipients = [participant for participant in participants if participant is not speaker]
            message = speaker.get_component(Communication_Policy).send_message(recipients, env)
            for recipient in recipients:
                recipient.get_component(Communication_Policy).receive_message(message, speaker, env)

    for participant in participants:
        participant.get_component(Communication_Policy).end_conversation(participants, env)


def run_exp(model_mode: str = "human_action", total_races: int = 8, conversation_turns: int = 2):
    if model_mode == "human_action":
        agents = [
            Entity(
                name="Rower A",
                position=Boat_Position(),
                actions=[Paddle(), Wait()],
                components=[Human_Takes_Action(), Human_Communication_Policy()],
            ),
            Entity(
                name="Rower B",
                position=Boat_Position(),
                actions=[Paddle(), Wait()],
                components=[Human_Takes_Action(), Human_Communication_Policy()],
            ),
        ]
    else:
        key_a, key_b = register_models(model_mode)
        agents = build_boat_race_agents(
            build_llm_policy(key_a),
            build_llm_policy(key_b),
        )

    env = Boat_Race(
        description="Minimal cooperative boat race benchmark.",
        agents=agents,
        total_races=total_races,
    )

    participants = env.agents
    last_race_index = -1
    max_total_steps = env.total_races * env.race_duration
    for _step_idx in range(max_total_steps):
        if env.current_race_index != last_race_index:
            if all(participant.has_component(Communication_Policy) for participant in participants):
                run_conversation_round(participants, env, env.current_race_index, conversation_turns)
            last_race_index = env.current_race_index

        cur_step_actions = []
        for agent_id, controlled_agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = controlled_agent.get_component(Agent_Policy).select_action(observation)
            print(
                f"[race {env.current_race_index + 1} step {env.race_step}] "
                f"{controlled_agent.name} -> {action}"
            )
            if info:
                if info.get("reasoning"):
                    print(f"[race {env.current_race_index + 1} step {env.race_step}] reasoning:\n{info['reasoning']}")
                if info.get("raw_response"):
                    print(f"[race {env.current_race_index + 1} step {env.race_step}] raw response:\n{info['raw_response']}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)
        print(
            f"[race {env.current_race_index + 1}] progress={env.boat_progress}/{env.goal_progress} "
            f"choices={env.last_round_choices}"
        )

        if all(env.terminations):
            print(
                f"Episode ended at race {env.current_race_index + 1}. "
                f"reached_goal={env.reached_goal} failed={env.failed}"
            )
            break


if __name__ == "__main__":
    run_exp(sys.argv[1] if len(sys.argv) > 1 else "human_action")
