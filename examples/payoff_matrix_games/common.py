from __future__ import annotations

import argparse
import csv
import json
import os

from word_play.core import (
    Action,
    Action_Selection,
    Agent_Policy,
    Component,
    Entity,
    Environment,
    Observation,
    Target_Is_Nearby,
)
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import (
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model
from word_play.presets.movement.single_point import (
    SINGLE_POINT_MOVEMENT_SYSTEM,
    Single_Point_Position,
)
from word_play.presets.observation.simple_observation import Simple_Observation
from word_play.presets.observation.utils import entity_state_to_str
from word_play.presets.systems.communication import (
    Communication_Policy,
    Human_Communication_Policy,
)


class Payoff_Matrix(Component):
    def __init__(
        self,
        *,
        game_name: str,
        action_names: list[str],
        payoff_matrix: list[list[list[float] | tuple[float, float]]],
        objective_text: str,
        auto_add_payoff_matrix_actions_to_all_agents: bool = True,
    ):
        super().__init__()
        if len(action_names) < 2:
            raise ValueError("Payoff_Matrix requires at least two actions.")
        if not isinstance(auto_add_payoff_matrix_actions_to_all_agents, bool):
            raise TypeError("auto_add_payoff_matrix_actions_to_all_agents must be a bool.")

        matrix_size = len(action_names)
        if len(payoff_matrix) != matrix_size:
            raise ValueError("Payoff matrix must have one row per action.")

        normalized_matrix: list[list[tuple[float, float]]] = []
        for row in payoff_matrix:
            if len(row) != matrix_size:
                raise ValueError("Payoff matrix must be square.")
            normalized_row: list[tuple[float, float]] = []
            for cell in row:
                if len(cell) != 2:
                    raise ValueError("Each payoff cell must contain exactly two rewards.")
                normalized_row.append((float(cell[0]), float(cell[1])))
            normalized_matrix.append(normalized_row)

        self.game_name = game_name
        self.action_names = list(action_names)
        self.payoff_matrix = normalized_matrix
        self.objective_text = objective_text
        self.auto_add_payoff_matrix_actions_to_all_agents = auto_add_payoff_matrix_actions_to_all_agents

        self.pending_rewards: list[float] = []
        self.current_step_choices: dict[str, int] = {}
        self.last_joint_actions: dict[str, str] | None = None
        self.last_payoffs: dict[str, float] | None = None
        self.cumulative_rewards: dict[str, float] = {}

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        if self.auto_add_payoff_matrix_actions_to_all_agents:
            self._ensure_actions(env.agents)

        participant_agents = self.participant_agents(env)
        if len(participant_agents) != 2:
            raise ValueError("Payoff_Matrix requires exactly two participating agents.")

        for agent in participant_agents:
            self.cumulative_rewards.setdefault(agent.name, 0.0)

    def pre_actions_step(self, env: Environment) -> None:
        self.pending_rewards = [0.0 for _ in env.agents]
        self.current_step_choices = {}

    def choose_action(self, action_selection: "Payoff_Matrix_Action") -> None:
        if not (0 <= action_selection.action_index < len(self.action_names)):
            raise ValueError(f"Invalid payoff-matrix action index: {action_selection.action_index}")
        self.current_step_choices[action_selection.entity.name] = action_selection.action_index

    def post_actions_step(self, env: Environment) -> None:
        participant_agents = self.participant_agents(env)
        missing_agents = [
            agent.name for agent in participant_agents if agent.name not in self.current_step_choices
        ]
        if missing_agents:
            raise ValueError(
                f"Missing payoff-matrix actions for: {', '.join(missing_agents)}"
            )

        first_action_idx = self.current_step_choices[participant_agents[0].name]
        second_action_idx = self.current_step_choices[participant_agents[1].name]
        payoffs = self.payoff_matrix[first_action_idx][second_action_idx]

        self.pending_rewards = [0.0 for _ in env.agents]
        for agent, reward in zip(participant_agents, payoffs):
            self.pending_rewards[env.agent_to_idx[agent]] = reward
            self.cumulative_rewards[agent.name] = self.cumulative_rewards.get(agent.name, 0.0) + reward

        self.last_joint_actions = {
            participant_agents[0].name: self.action_names[first_action_idx],
            participant_agents[1].name: self.action_names[second_action_idx],
        }
        self.last_payoffs = {
            participant_agents[0].name: payoffs[0],
            participant_agents[1].name: payoffs[1],
        }

        step_info = {
            "joint_actions": self.last_joint_actions.copy(),
            "payoffs": self.last_payoffs.copy(),
            "step_count": env.step_count + 1,
            "cumulative_rewards": {
                agent.name: self.cumulative_rewards[agent.name]
                for agent in participant_agents
            },
        }
        for agent in env.agents:
            env.infos[env.agent_to_idx[agent]]["action_info"] = step_info

        env.step_count += 1
        if env.step_count >= env.max_steps:
            env.truncations = [True for _ in env.agents]

    def cumulative_reward_for(self, agent_name: str) -> float:
        return self.cumulative_rewards.get(agent_name, 0.0)

    def observation_sections(
        self,
        *,
        agent_name: str,
        step_count: int,
        max_steps: int,
    ) -> tuple[str, ...]:
        sections = [self.objective_text]

        if self.last_joint_actions is not None and self.last_payoffs is not None:
            sections.append( # this step basically just shows the last action and the payoff for that action (ensuring that this is not the first step)
                "\n".join(
                    [
                        "LAST STEP RESULT:",
                        f"  joint_actions: {self.last_joint_actions}",
                        f"  payoffs: {self.last_payoffs}",
                    ]
                )
            )

        steps_remaining = max(0, max_steps - step_count)
        sections.append(
            "\n".join(
                [
                    "GAME STATE:",
                    f"  game_name: {self.game_name}",
                    f"  step_count: {step_count}/{max_steps}",
                    f"  steps_remaining: {steps_remaining}",
                    f"  cumulative_reward: {self.cumulative_reward_for(agent_name):+.2f}",
                ]
            )
        )
        return tuple(sections)

    def participant_agents(self, env: Environment) -> list[Entity]:
        if self.auto_add_payoff_matrix_actions_to_all_agents:
            return list(env.agents)

        return [
            agent
            for agent in env.agents
            if any(isinstance(action, Payoff_Matrix_Action) for action in agent.actions)
        ]

    def _ensure_actions(self, participant_agents: list[Entity]) -> None:
        # this ensures that each agent has an action for each action in the payoff matrix
        # we call this on instantiation 
        for agent in participant_agents:
            existing_action_indices = {
                action.action_index
                for action in agent.actions
                if isinstance(action, Payoff_Matrix_Action)
            }
            for action_index, action_name in enumerate(self.action_names):
                if action_index in existing_action_indices:
                    continue
                agent.actions.append(
                    Payoff_Matrix_Action(
                        action_index=action_index,
                        action_name=action_name,
                    )
                )
            """
            for reference, it would look something like this:
                agent.actions = [
                    Payoff_Matrix_Action(action_index=0, action_name="Cooperate"),
                    Payoff_Matrix_Action(action_index=1, action_name="Defect"),
                ]

            """


class Payoff_Matrix_Action(Action):
    def __init__(self, action_index: int, action_name: str):
        self.action_index = action_index
        self.action_name = action_name
        self.entity: Entity | None = None
        super().__init__(
            validation_rules=[
                Target_Is_Nearby(),
                Target_Has_Component(Payoff_Matrix),
            ]
        )

    def exec_action(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None
    ) -> dict | None:
        payoff_matrix = target_entity.get_component(Payoff_Matrix)
        if payoff_matrix is None:
            raise ValueError("Payoff_Matrix_Action requires a target with Payoff_Matrix.")
        self.entity = actor
        payoff_matrix.choose_action(self)
        return {"action_index": self.action_index, "action_name": self.action_name}

    def action_description_text(
        self, actor: Entity, target_entity: Entity, env: Environment
    ) -> str:
        return f"Choose action: {self.action_name}."


def format_payoff_matrix_nearby_entities(nearby_entities: list[Entity], agent: Entity) -> str:
    lines = []
    for entity in nearby_entities:
        if entity is agent:
            continue
        payoff_matrix = entity.get_component(Payoff_Matrix)
        if payoff_matrix is not None:
            lines.append(
                "\n".join(
                    [
                        f"- name: {entity.name}",
                        f"  position: {entity.position}",
                        f"  payoff_matrix_actions: {payoff_matrix.action_names}",
                    ]
                )
            )
        else:
            lines.append(f"- {entity_state_to_str(entity).replace(chr(10), chr(10) + '  ')}")

    if not lines:
        return "Nearby Entities: None"
    return "Nearby Entities:\n" + "\n".join(lines)


def payoff_matrix_reward(
    agent_actions: list[Action_Selection], env: "Payoff_Matrix_Environment"
) -> list[float]:
    return env.get_payoff_matrix_component().pending_rewards.copy()


class Payoff_Matrix_Environment(Simple_Env_Reset_Mixin, Environment):
    def __init__(
        self,
        description: str,
        entities: list[Entity],
        *,
        max_steps: int = 20,
    ):
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")

        payoff_matrix_entities = [
            entity for entity in entities if entity.get_component(Payoff_Matrix) is not None
        ]
        if len(payoff_matrix_entities) != 1:
            raise ValueError("Payoff_Matrix_Environment requires exactly one Payoff_Matrix entity.")

        self.max_steps = max_steps
        self.step_count = 0

        super().__init__(
            description=description,
            entities=entities,
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=payoff_matrix_reward,
            entity_order=entity_definition_order,
        )

    def _reset(self, seed=None) -> None:
        super()._reset(seed=seed)
        self.step_count = 0

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        payoff_matrix = self.get_payoff_matrix_component()
        last_reward = self.last_rewards[agent_id]
        return Simple_Observation(
            possible_actions=self.possible_actions(agent),
            nearby_entities=self.entities_near_position(agent.position),
            agent=agent,
            last_reward=0.0 if last_reward is None else last_reward,
            info=self.infos[agent_id],
            observation_radius=0,
            extra_sections=payoff_matrix.observation_sections(
                agent_name=agent.name,
                step_count=self.step_count,
                max_steps=self.max_steps,
            ),
            nearby_entities_formatter=format_payoff_matrix_nearby_entities,
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    # TODO: something to think about, maybe we should have these 2 functions above be abstract method in Environment class?

    def get_payoff_matrix_component(self) -> Payoff_Matrix:
        for entity in self.state.entities:
            payoff_matrix = entity.get_component(Payoff_Matrix)
            if payoff_matrix is not None:
                return payoff_matrix
        raise ValueError("No Payoff_Matrix component found in environment state.")


def register_model(model_mode: str, game_name: str) -> str:
    model_key = f"payoff_matrix_{game_name}_{model_mode}"
    system_prompt = (
        f"You are playing the game: {game_name}. "
        "Each step you must choose exactly one action from the available actions. "
        'Respond only with JSON: {"action_choice_idx": <integer>}.'
    )

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

    raise ValueError(f"Unsupported model_mode: {model_mode}")


def make_policy(model_mode: str, model_key: str | None):
    if model_mode == "human_action":
        return Human_Takes_Action()

    action_generation_config = None
    if model_mode == "openrouter_large":
        action_generation_config = {
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": "minimal", "exclude": True},
            "verbosity": "low",
        }

    return LLM_Action_And_Communication_Policy(
        model_key=model_key,
        action_generation_config=action_generation_config,
        action_max_new_tokens=512,
        observation_memory_window=2,
        max_stored_observation_chars=1500,
    )

# added this function to build the entities for payoff matrix games, but 
# we might not need it, but since most of the payoff matrix games have 2 agents and to 
# avoid repeating code, it's added here for now:

def build_entities(
    *,
    game_name: str,
    action_names: list[str],
    payoff_matrix: list[list[list[float] | tuple[float, float]]],
    objective_text: str,
    model_mode: str,
    communication_enabled: bool = False,
    auto_add_payoff_matrix_actions_to_all_agents: bool = True,
) -> list[Entity]:
    model_key = register_model(model_mode, game_name) if model_mode != "human_action" else None
    agent_entities: list[Entity] = []
    for idx in range(2):
        components = [make_policy(model_mode, model_key)]
        if communication_enabled and model_mode == "human_action":
            components.append(Human_Communication_Policy())
        agent_entities.append(
            Entity(
                name=f"Agent {chr(ord('A') + idx)}",
                position=Single_Point_Position(),
                components=components,
            )
        )

    voting_box = build_payoff_matrix_voting_box(
        game_name=game_name,
        action_names=action_names,
        payoff_matrix=payoff_matrix,
        objective_text=objective_text,
        auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
    )
    return [*agent_entities, voting_box]


def build_payoff_matrix_voting_box(
    *,
    game_name: str,
    action_names: list[str],
    payoff_matrix: list[list[list[float] | tuple[float, float]]],
    objective_text: str,
    auto_add_payoff_matrix_actions_to_all_agents: bool = True,
    name: str = "Voting Box",
) -> Entity:
    return Entity(
        name=name,
        position=Single_Point_Position(),
        components=[
            Payoff_Matrix(
                game_name=game_name,
                action_names=action_names,
                payoff_matrix=payoff_matrix,
                objective_text=objective_text,
                auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
            )
        ],
    )


def run_communication_phase(agents: list[Entity], env: Payoff_Matrix_Environment, step_count: int) -> None:
    for agent in agents:
        if agent.get_component(Communication_Policy) is None:
            return

    for speaker in agents:
        communication_policy = speaker.get_component(Communication_Policy)
        recipients = [agent for agent in agents if agent is not speaker]
        communication_policy.start_conversation(
            agents,
            env,
            info=f"Pre-action communication, step {step_count}.",
        )
        message = communication_policy.send_message(recipients, env)
        for recipient in recipients:
            recipient.get_component(Communication_Policy).receive_message(message, speaker, env)
        communication_policy.end_conversation(agents, env)


def run_payoff_matrix_game(
    *,
    game_name: str,
    action_names: list[str],
    payoff_matrix: list[list[list[float] | tuple[float, float]]],
    objective_text: str,
    model_mode: str = "human_action",
    max_steps: int = 20,
    log_path: str | None = None,
    communication_enabled: bool = False,
    auto_add_payoff_matrix_actions_to_all_agents: bool = True,
) -> None:
    entities = build_entities(
        game_name=game_name,
        action_names=action_names,
        payoff_matrix=payoff_matrix,
        objective_text=objective_text,
        model_mode=model_mode,
        communication_enabled=communication_enabled,
        auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
    )
    env = Payoff_Matrix_Environment(
        description=game_name,
        entities=entities,
        max_steps=max_steps,
    )

    print(f"\n{'=' * 60}")
    print(f"  Game : {game_name}")
    print(f"  Mode : {model_mode}")
    print(f"  Steps: {max_steps}")
    print(f"  Players: {[agent.name for agent in env.agents]}")
    print(f"{'=' * 60}\n")

    payoff_matrix_component = env.get_payoff_matrix_component()
    cumulative_rewards = [0.0] * len(env.agents)
    csv_file = None
    log_writer = None

    if log_path:
        parent_dir = os.path.dirname(log_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        csv_file = open(log_path, "w", newline="")
        log_writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "step",
                "game_name",
                "model_mode",
                "observations",
                "actions",
                "selection_info",
                "joint_actions",
                "payoffs",
                "rewards",
                "cumulative_rewards",
                "infos",
                "terminations",
                "truncations",
            ],
        )
        log_writer.writeheader()
        csv_file.flush()

    try:
        for step_idx in range(max_steps):
            current_step_log: dict[str, object] = {
                "step": step_idx,
                "game_name": game_name,
                "model_mode": model_mode,
            }
            if communication_enabled:
                run_communication_phase(env.agents, env, step_idx)

            current_step_actions = []
            observations_by_agent: dict[str, str] = {}
            actions_by_agent: dict[str, str] = {}
            selection_info_by_agent: dict[str, dict] = {}
            
            for agent_id, agent in enumerate(env.agents):
                observation = env.observe(agent_id)
                observations_by_agent[agent.name] = str(observation)
                action, info = agent.get_component(Agent_Policy).select_action(observation)
                current_step_actions.append(action)
                actions_by_agent[agent.name] = str(action)
                selection_info_by_agent[agent.name] = info or {}
                if info and info.get("raw_response"):
                    print(f"  [{agent.name}] raw: {info['raw_response'].strip()}")

            env.step(current_step_actions)

            for agent_idx, agent in enumerate(env.agents):
                cumulative_rewards[agent_idx] = payoff_matrix_component.cumulative_reward_for(agent.name)

            print(
                f"[step {step_idx:>3}]  joint_actions: {payoff_matrix_component.last_joint_actions}"
            )
            print(
                f"           payoffs: {payoff_matrix_component.last_payoffs}  |  cumulative: "
                f"{ {agent.name: cumulative_rewards[idx] for idx, agent in enumerate(env.agents)} }"
            )

            current_step_log["observations"] = observations_by_agent
            current_step_log["actions"] = actions_by_agent
            current_step_log["selection_info"] = selection_info_by_agent
            current_step_log["joint_actions"] = payoff_matrix_component.last_joint_actions
            current_step_log["payoffs"] = payoff_matrix_component.last_payoffs
            current_step_log["rewards"] = {
                agent.name: env.last_rewards[agent_idx]
                for agent_idx, agent in enumerate(env.agents)
            }
            current_step_log["cumulative_rewards"] = {
                agent.name: cumulative_rewards[agent_idx]
                for agent_idx, agent in enumerate(env.agents)
            }
            current_step_log["infos"] = {
                agent.name: env.infos[agent_idx]
                for agent_idx, agent in enumerate(env.agents)
            }
            current_step_log["terminations"] = env.terminations
            current_step_log["truncations"] = env.truncations

            if log_writer is not None:
                log_writer.writerow(
                    {
                        key: json.dumps(value, default=str)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in current_step_log.items()
                    }
                )
                csv_file.flush()

            if any(env.terminations):
                print(f"\nEpisode terminated at step {step_idx + 1}.")
                break
            if any(env.truncations):
                print(f"\nReached max steps ({max_steps}).")
                break
    finally:
        if csv_file is not None:
            csv_file.close()
            print(f"Saved log to {log_path}")

    print(f"\n{'=' * 60}")
    print("  FINAL CUMULATIVE REWARDS")
    for agent_idx, agent in enumerate(env.agents):
        print(f"    {agent.name}: {cumulative_rewards[agent_idx]:+.2f}")
    print(f"{'=' * 60}\n")


def parse_common_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a payoff-matrix game example.")
    parser.add_argument(
        "model_mode",
        nargs="?",
        default="human_action",
        choices=["human_action", "human_llm", "openrouter_small", "openrouter_mid", "openrouter_large"],
    )
    parser.add_argument("--max_steps", type=int, default=20)
    parser.add_argument("--max_rounds", type=int, dest="max_steps_legacy", default=None)
    parser.add_argument("--log", dest="log_path", default=None)
    parser.add_argument("--reward_log", dest="log_path", default=None)
    return parser.parse_args()
