from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from word_play.core import (  # noqa: E402
    Action,
    Action_Selection,
    Agent_Policy,
    Entity,
    Environment,
    Observation,
    Target_Is_Self,
)
from word_play.presets.action_policies.llm_action_and_communication import (  # noqa: E402
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.entity_orderings import entity_definition_order  # noqa: E402
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model, register_model  # noqa: E402
from word_play.presets.movement.single_point import (  # noqa: E402
    SINGLE_POINT_MOVEMENT_SYSTEM,
    Single_Point_Position,
)
from word_play.presets.observation.simple_observation import Simple_Observation  # noqa: E402
from word_play.presets.systems.communication.core import Communication_Policy  # noqa: E402


class Play_Signal(Action):

    def __init__(self, signal_value: int):
        self.signal_value = signal_value
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict:
        return {"signal": self.signal_value}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Play signal {self.signal_value}."


def private_sum_reward(agent_actions: list[Action_Selection], env: "Private_Sum_Env") -> list[float]:
    return env.round_rewards.copy()


class Private_Sum_Env(Environment):
    agent_names = ("Agent A", "Agent B", "Agent C")

    def __init__(
        self,
        model_key: str,
        private_signals: tuple[int, int, int] = (1, 3, 4),
        signal_modulus: int = 5,
        action_generation_config: dict | None = None,
        message_generation_config: dict | None = None,
    ):
        self.private_signals = dict(zip(self.agent_names, private_signals))
        self.signal_modulus = signal_modulus
        self.expected_signal = sum(private_signals) % signal_modulus
        self.round_choices: dict[str, int] = {}
        self.round_rewards = [0.0, 0.0, 0.0]
        self.team_status = "not_started"

        entities = [
            Entity(
                name=agent_name,
                position=Single_Point_Position(),
                actions=[Play_Signal(signal_value) for signal_value in range(signal_modulus)],
                components=[
                    LLM_Action_And_Communication_Policy(
                        model_key=model_key,
                        system_prompt=(
                            "You are one agent in a three-agent coordination game. "
                            "When asked to communicate, tell teammates your private signal as a short sentence. "
                            "When choosing an action, use your private signal plus teammate messages. "
                            "Return action selections only as the requested JSON object."
                        ),
                        action_generation_config=action_generation_config,
                        message_generation_config=message_generation_config,
                        action_max_new_tokens=512,
                        message_max_new_tokens=128,
                    )
                ],
            )
            for agent_name in self.agent_names
        ]

        super().__init__(
            description="Three-agent private-signal communication demo.",
            entities=entities,
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=private_sum_reward,
            entity_order=entity_definition_order,
        )

    def private_signal_for(self, agent_name: str) -> int:
        return self.private_signals[agent_name]

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        teammate_names = [other.name for other in self.agents if other is not agent]

        return Simple_Observation(
            possible_actions=self.possible_actions(agent),
            nearby_entities=self.entities_near_position(agent.position),
            agent=agent,
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
            extra_sections=(
                "\n".join(
                    [
                        "OBJECTIVE:",
                        "  All agents must play the same correct signal.",
                        "  Correct signal = sum(all private signals) mod signal_modulus.",
                        "  Use the recent conversation messages to infer teammate signals.",
                    ]
                ),
                "\n".join(
                    [
                        "PRIVATE SIGNAL STATE:",
                        f"  your_private_signal: {self.private_signal_for(agent.name)}",
                        f"  teammates: {', '.join(teammate_names)}",
                        f"  signal_modulus: {self.signal_modulus}",
                    ]
                ),
            ),
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]):
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]):
        self.round_choices = {}
        chosen_signals = []

        for action_selection in action_selections:
            if not isinstance(action_selection.action, Play_Signal):
                raise TypeError("Private_Sum_Env only supports Play_Signal actions.")
            signal_value = action_selection.action.signal_value
            self.round_choices[action_selection.actor.name] = signal_value
            chosen_signals.append(signal_value)

        all_correct = all(signal_value == self.expected_signal for signal_value in chosen_signals)
        fully_coordinated = len(set(chosen_signals)) == 1

        if all_correct:
            self.round_rewards = [1.0 for _agent in self.agents]
            self.team_status = "correct"
            self.terminations = [True for _agent in self.agents]
        elif fully_coordinated:
            self.round_rewards = [-0.25 for _agent in self.agents]
            self.team_status = "coordinated_but_wrong"
            self.truncations = [True for _agent in self.agents]
        else:
            self.round_rewards = [-0.75 for _agent in self.agents]
            self.team_status = "miscoordinated"
            self.truncations = [True for _agent in self.agents]

        for info in self.infos:
            info["action_info"] = {
                "team_status": self.team_status,
                "expected_signal": self.expected_signal,
                "choices": self.round_choices.copy(),
            }

    def _reset(self, seed=None):
        self.round_choices = {}
        self.round_rewards = [0.0, 0.0, 0.0]
        self.team_status = "not_started"


def run_communication_phase(env: Private_Sum_Env) -> list[dict[str, object]]:
    transcript = []

    for agent in env.agents:
        agent.get_component(Communication_Policy).start_conversation(
            env.agents,
            env,
            info="Share your private signal with the team.",
        )

    for speaker in env.agents:
        recipients = [agent for agent in env.agents if agent is not speaker]
        message = speaker.get_component(Communication_Policy).send_message(
            recipients,
            env,
            info=f"Your private signal is {env.private_signal_for(speaker.name)}.",
        )
        transcript.append(
            {
                "sender": speaker.name,
                "recipients": [recipient.name for recipient in recipients],
                "message": message,
            }
        )

        for recipient in recipients:
            recipient.get_component(Communication_Policy).receive_message(message, speaker, env)

    for agent in env.agents:
        agent.get_component(Communication_Policy).end_conversation(env.agents, env)

    return transcript


def run_action_phase(env: Private_Sum_Env) -> list[dict[str, object]]:
    cur_step_actions = []
    action_history = []

    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        action, info = agent.get_component(Agent_Policy).select_action(observation)
        cur_step_actions.append(action)
        action_history.append(
            {
                "agent_id": agent_id,
                "agent": agent.name,
                "private_signal": env.private_signal_for(agent.name),
                "action": str(action),
                "raw_response": info.get("raw_response"),
            }
        )

    env.step(cur_step_actions)

    for row in action_history:
        row["reward"] = env.last_rewards[row["agent_id"]]
    return action_history


def run_exp():
    model_key = "three_agent_communication_openrouter"
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

    env = Private_Sum_Env(
        model_key=model_key,
        private_signals=(1, 3, 4),
        signal_modulus=5,
        action_generation_config={
            **openrouter_config,
            "response_format": {"type": "json_object"},
        },
        message_generation_config=openrouter_config,
    )

    print("Three-agent LLM communication demo")
    print(f"OpenRouter model: {model_name}")
    print(f"Private signals, printed for verification: {env.private_signals}")
    print(f"Correct team signal: {env.expected_signal}\n")

    transcript = run_communication_phase(env)
    print("Communication transcript:")
    for turn in transcript:
        recipients = ", ".join(turn["recipients"])
        print(f"  {turn['sender']} -> {recipients}: {turn['message']}")

    action_history = run_action_phase(env)
    print("\nAction history:")
    for row in action_history:
        print(
            f"  {row['agent']} "
            f"private_signal={row['private_signal']} "
            f"action={row['action']} "
            f"reward={row['reward']} "
            f"raw={row['raw_response']}"
        )

    print("\nSummary:")
    print(f"  expected_signal: {env.expected_signal}")
    print(f"  choices: {env.round_choices}")
    print(f"  rewards: {env.round_rewards}")
    print(f"  team_status: {env.team_status}")


if __name__ == "__main__":
    run_exp()
