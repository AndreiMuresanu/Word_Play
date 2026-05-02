from __future__ import annotations

import contextlib
import csv
import json
import os
from typing import Iterator

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
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
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
from word_play.presets.systems.do_nothing import Do_Nothing

from .expand_symmetric_payoff_matrix import expand_symmetric_payoff_matrix

try:
    from .model_params import SUPPORTED_MODEL_MODES, make_policy, register_model
except ImportError:
    from model_params import SUPPORTED_MODEL_MODES, make_policy, register_model


class Payoff_Matrix(Component):
    """
    Manages payoff resolution for a simultaneous-move stage game.

    Manages payoff resolution for a simultaneous-move stage game.

    The payoff matrix is specified as a symmetric single-player row and
    automatically expanded to the full N-player matrix via
    `expand_symmetric_payoff_matrix`.

    Action names are provided as a flat list whose length must match the
    number of rows in the payoff matrix.  Each name maps 1-to-1 to an action
    index, which is what agents submit when voting.

    Parameters
    ----------
    game_name:
        Human-readable name shown in observations.
    num_players:
        Number of players participating in the game. Must be >= 2.
    action_names:
        Ordered list of strategy labels.  Length must equal the number of
        actions (top-level entries) in `payoff_matrix`.
    payoff_matrix:
        Single-player payoff row (symmetric game input).  Passed directly to
        `expand_symmetric_payoff_matrix`.  See that function's docstring for
        the exact expected shape.

        Example (2-player Prisoner's Dilemma, actions [Cooperate, Defect]):
            [[3, 0],   # Cooperate vs [C, D]
             [5, 1]]   # Defect    vs [C, D]

    objective_text:
        Multi-line string shown to agents each step.  Describe the game rules
        and payoff structure here.  Stays constant across steps.
    auto_add_payoff_matrix_actions_to_all_agents:
        If True (default), voting actions are automatically added to every
        agent in the environment on instantiation.  Set to False if you want
        to control which agents have voting actions manually.
    """

    def __init__(
        self,
        *,
        game_name: str,
        num_players: int = 2,
        action_names: list[str],
        payoff_matrix: list,
        objective_text: str,
        auto_add_payoff_matrix_actions_to_all_agents: bool = True,
    ):
        super().__init__()

        if num_players < 2:
            raise ValueError("Payoff_Matrix requires at least two players.")
        if len(action_names) < 2:
            raise ValueError("Payoff_Matrix requires at least two action names.")
        if len(action_names) != len(payoff_matrix):
            raise ValueError(
                f"action_names has {len(action_names)} entries but payoff_matrix has "
                f"{len(payoff_matrix)} rows. They must match."
            )
        if not isinstance(auto_add_payoff_matrix_actions_to_all_agents, bool):
            raise TypeError("auto_add_payoff_matrix_actions_to_all_agents must be a bool.")

        self.game_name = game_name
        self.num_players = num_players
        self.action_names = list(action_names)
        self.objective_text = objective_text
        self.auto_add_payoff_matrix_actions_to_all_agents = auto_add_payoff_matrix_actions_to_all_agents
        self.payoff_matrix = expand_symmetric_payoff_matrix(payoff_matrix, num_players=num_players)

        self.pending_rewards: list[float] = []
        self.current_round_votes: dict[Entity, int] = {}
        self.last_joint_actions: dict[str, str] | None = None
        self.last_payoffs: dict[str, float] | None = None

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        if len(env.agents) < self.num_players:
            raise ValueError(
                f"Payoff_Matrix requires at least {self.num_players} agents "
                f"but only {len(env.agents)} are present."
            )
        if self.auto_add_payoff_matrix_actions_to_all_agents:
            self._ensure_actions(env)

    def pre_actions_step(self, env: Environment) -> None:
        self.pending_rewards = [0.0] * len(env.agents)

    def choose_action(self, actor: Entity, action_index: int) -> None:
        if not (0 <= action_index < len(self.action_names)):
            raise ValueError(f"Invalid action index: {action_index}")
        if actor in self.current_round_votes:
            return  # duplicate vote — no-op
        if len(self.current_round_votes) >= self.num_players:
            return  # already have enough votes — no-op
        self.current_round_votes[actor] = action_index

    def post_actions_step(self, env: Environment) -> None:
        step_info: dict[str, object] = {
            "step_count": env.step_count + 1,
            "votes_received": len(self.current_round_votes),
            "votes_needed": self.num_players,
            "current_votes": {
                agent.name: self.action_names[idx]
                for agent, idx in self.current_round_votes.items()
            },
        }

        if len(self.current_round_votes) == self.num_players:
            voting_agents = list(self.current_round_votes.keys())
            action_indices = list(self.current_round_votes.values())

            # Index into the N-dimensional matrix
            payoffs = self.payoff_matrix
            for idx in action_indices:
                payoffs = payoffs[idx]

            for agent, reward in zip(voting_agents, payoffs):
                self.pending_rewards[env.agent_to_idx[agent]] = reward

            self.last_joint_actions = {
                agent.name: self.action_names[idx]
                for agent, idx in zip(voting_agents, action_indices)
            }
            self.last_payoffs = {
                agent.name: float(reward)
                for agent, reward in zip(voting_agents, payoffs)
            }
            step_info["vote_status"] = "resolved"
            step_info["joint_actions"] = self.last_joint_actions.copy()
            step_info["payoffs"] = self.last_payoffs.copy()
            self.current_round_votes = {}
        else:
            step_info["vote_status"] = "collecting"

        for agent in env.agents:
            env.infos[env.agent_to_idx[agent]]["action_info"] = step_info

        env.step_count += 1
        if env.step_count >= env.max_steps:
            env.truncations = [True] * len(env.agents)

    def observation_sections(self, *, step_count: int, max_steps: int) -> tuple[str, ...]:
        sections = [self.objective_text]

        if self.last_joint_actions is not None and self.last_payoffs is not None:
            sections.append("\n".join([
                "LAST ROUND RESULT:",
                f"  joint_actions: {self.last_joint_actions}",
                f"  payoffs: {self.last_payoffs}",
            ]))

        sections.append("\n".join([
            "VOTING BOX STATUS:",
            f"  votes_received: {len(self.current_round_votes)}/{self.num_players}",
            f"  current_votes: { {a.name: self.action_names[i] for a, i in self.current_round_votes.items()} }",
        ]))

        sections.append("\n".join([
            "GAME STATE:",
            f"  game_name: {self.game_name}",
            f"  step_count: {step_count}/{max_steps}",
            f"  steps_remaining: {max(0, max_steps - step_count)}",
        ]))

        return tuple(sections)

    def _ensure_actions(self, env: Environment) -> None:
        for agent in env.agents:
            existing = {
                action.action_index
                for action in agent.actions
                if isinstance(action, Payoff_Matrix_Action)
            }
            for idx, name in enumerate(self.action_names):
                if idx not in existing:
                    agent.actions.append(Payoff_Matrix_Action(action_index=idx, action_name=name))


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

class Payoff_Matrix_Action(Action):
    def __init__(self, action_index: int, action_name: str):
        self.action_index = action_index
        self.action_name = action_name
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
            raise ValueError("Payoff_Matrix_Action requires a target with a Payoff_Matrix component.")
        payoff_matrix.choose_action(actor, self.action_index)
        return None

    def action_description_text(
        self, actor: Entity, target_entity: Entity, env: Environment
    ) -> str:
        return f"Choose action: {self.action_name}."


# ---------------------------------------------------------------------------
# Observation formatter
# ---------------------------------------------------------------------------

def format_payoff_matrix_nearby_entities(nearby_entities: list[Entity], agent: Entity) -> str:
    lines = []
    for entity in nearby_entities:
        if entity is agent:
            continue
        pm = entity.get_component(Payoff_Matrix)
        if pm is not None:
            lines.append("\n".join([
                f"- name: {entity.name}",
                f"  position: {entity.position}",
                f"  available_actions: {pm.action_names}",
            ]))
        else:
            lines.append(f"- {entity_state_to_str(entity).replace(chr(10), chr(10) + '  ')}")

    return "Nearby Entities:\n" + "\n".join(lines) if lines else "Nearby Entities: None"


# ---------------------------------------------------------------------------
# Reward function
# ---------------------------------------------------------------------------

def payoff_matrix_reward(
    agent_actions: list[Action_Selection], env: "Payoff_Matrix_Environment"
) -> list[float]:
    return env.get_payoff_matrix_component().pending_rewards.copy()


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class Payoff_Matrix_Environment(Simple_Env_Reset_Mixin, Environment):
    def __init__(self, description: str, entities: list[Entity], *, max_steps: int = 20):
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")

        pm_entities = [e for e in entities if e.get_component(Payoff_Matrix) is not None]
        if len(pm_entities) != 1:
            raise ValueError("Payoff_Matrix_Environment requires exactly one entity with a Payoff_Matrix component.")

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

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        pm = self.get_payoff_matrix_component()
        last_reward = self.last_rewards[agent_id]
        return Simple_Observation(
            possible_actions=self.possible_actions(agent),
            nearby_entities=self.entities_near_position(agent.position),
            agent=agent,
            last_reward=0.0 if last_reward is None else last_reward,
            info=self.infos[agent_id],
            observation_radius=0,
            extra_sections=pm.observation_sections(
                step_count=self.step_count,
                max_steps=self.max_steps,
            ),
            nearby_entities_formatter=format_payoff_matrix_nearby_entities,
        )

    def get_payoff_matrix_component(self) -> Payoff_Matrix:
        for entity in self.state.entities:
            pm = entity.get_component(Payoff_Matrix)
            if pm is not None:
                return pm
        raise ValueError("No Payoff_Matrix component found in environment.")


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def build_payoff_matrix_voting_box(
    *,
    game_name: str,
    num_players: int = 2,
    action_names: list[str],
    payoff_matrix: list,
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
                num_players=num_players,
                action_names=action_names,
                payoff_matrix=payoff_matrix,
                objective_text=objective_text,
                auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
            )
        ],
    )


def build_entities(
    *,
    game_name: str,
    action_names: list[str],
    payoff_matrix: list,
    objective_text: str,
    model_mode: str,
    num_players: int = 2,
    num_agents: int | None = None,
    communication_enabled: bool = False,
    auto_add_payoff_matrix_actions_to_all_agents: bool = True,
) -> list[Entity]:
    total_agents = num_players if num_agents is None else num_agents
    if total_agents < num_players:
        raise ValueError("num_agents must be at least num_players.")

    model_key = register_model(model_mode, game_name) if model_mode != "human_action" else None

    agent_entities = []
    for idx in range(total_agents):
        components = [make_policy(model_mode, model_key)]
        if communication_enabled and model_mode == "human_action":
            components.append(Human_Communication_Policy())
        agent_entities.append(Entity(
            name=f"Agent {chr(ord('A') + idx)}",
            position=Single_Point_Position(),
            actions=[Do_Nothing()],
            components=components,
        ))

    voting_box = build_payoff_matrix_voting_box(
        game_name=game_name,
        num_players=num_players,
        action_names=action_names,
        payoff_matrix=payoff_matrix,
        objective_text=objective_text,
        auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
    )
    return [*agent_entities, voting_box]


# ---------------------------------------------------------------------------
# Communication phase
# ---------------------------------------------------------------------------

def run_communication_phase(
    agents: list[Entity], env: Payoff_Matrix_Environment, step_count: int
) -> None:
    for agent in agents:
        if agent.get_component(Communication_Policy) is None:
            return

    for speaker in agents:
        comm = speaker.get_component(Communication_Policy)
        recipients = [a for a in agents if a is not speaker]
        comm.start_conversation(agents, env, info=f"Pre-action communication, step {step_count}.")
        message = comm.send_message(recipients, env)
        for recipient in recipients:
            recipient.get_component(Communication_Policy).receive_message(message, speaker, env)
        comm.end_conversation(agents, env)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _csv_log(log_path: str) -> Iterator[csv.DictWriter]:
    parent_dir = os.path.dirname(log_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "step", "game_name", "model_mode", "observations", "actions",
            "selection_info", "joint_actions", "payoffs", "rewards",
            "infos", "terminations", "truncations",
        ])
        writer.writeheader()
        yield writer


def run_payoff_matrix_game(
    *,
    game_name: str,
    action_names: list[str],
    payoff_matrix: list,
    objective_text: str,
    model_mode: str = "human_action",
    max_steps: int = 20,
    log_path: str | None = None,
    num_players: int = 2,
    num_agents: int | None = None,
    communication_enabled: bool = False,
    auto_add_payoff_matrix_actions_to_all_agents: bool = True,
) -> None:
    entities = build_entities(
        game_name=game_name,
        action_names=action_names,
        payoff_matrix=payoff_matrix,
        objective_text=objective_text,
        model_mode=model_mode,
        num_players=num_players,
        num_agents=num_agents,
        communication_enabled=communication_enabled,
        auto_add_payoff_matrix_actions_to_all_agents=auto_add_payoff_matrix_actions_to_all_agents,
    )
    env = Payoff_Matrix_Environment(description=game_name, entities=entities, max_steps=max_steps)
    pm = env.get_payoff_matrix_component()

    print(f"\n{'=' * 60}")
    print(f"  Game: {game_name}  |  Mode: {model_mode}  |  Steps: {max_steps}")
    print(f"  Players: {[a.name for a in env.agents]}")
    print(f"{'=' * 60}\n")

    log_ctx = _csv_log(log_path) if log_path else contextlib.nullcontext(None)

    with log_ctx as log_writer:
        for step_idx in range(max_steps):
            if communication_enabled:
                run_communication_phase(env.agents, env, step_idx)

            cur_step_actions = []
            observations, actions_str, selection_infos = {}, {}, {}

            for agent_id, agent in enumerate(env.agents):
                observation = env.observe(agent_id)
                action, info = agent.get_component(Agent_Policy).select_action(observation)
                cur_step_actions.append(action)
                observations[agent.name] = str(observation)
                actions_str[agent.name] = str(action)
                selection_infos[agent.name] = info or {}

                print(f"[step {step_idx}] {agent.name} -> {action}")
                if info:
                    if info.get("reasoning"):
                        print(f"[step {step_idx}] reasoning:\n{info['reasoning']}")
                    if info.get("raw_response"):
                        print(f"[step {step_idx}] raw response:\n{info['raw_response']}")

            env.step(cur_step_actions)

            print(f"           joint: {pm.last_joint_actions} | payoffs: {pm.last_payoffs}")

            if log_writer is not None:
                row = {
                    "step": step_idx,
                    "game_name": game_name,
                    "model_mode": model_mode,
                    "observations": observations,
                    "actions": actions_str,
                    "selection_info": selection_infos,
                    "joint_actions": pm.last_joint_actions,
                    "payoffs": pm.last_payoffs,
                    "rewards": {a.name: env.last_rewards[i] for i, a in enumerate(env.agents)},
                    "infos": {a.name: env.infos[i] for i, a in enumerate(env.agents)},
                    "terminations": env.terminations,
                    "truncations": env.truncations,
                }
                log_writer.writerow({
                    k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
                    for k, v in row.items()
                })

            if any(env.terminations):
                print(f"\nEpisode terminated at step {step_idx + 1}.")
                break
            if any(env.truncations):
                print(f"\nReached max steps ({max_steps}).")
                break

    if log_path:
        print(f"Saved log to {log_path}")


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def parse_common_args():
    import argparse
    parser = argparse.ArgumentParser(description="Run a payoff-matrix game.")
    parser.add_argument(
        "model_mode",
        nargs="?",
        default="human_action",
        choices=list(SUPPORTED_MODEL_MODES),
    )
    parser.add_argument("--max_steps", type=int, default=20)
    parser.add_argument("--log", dest="log_path", default=None)
    return parser.parse_args()