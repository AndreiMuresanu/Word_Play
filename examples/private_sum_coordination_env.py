from __future__ import annotations

import random
from dataclasses import dataclass

from word_play.core import (
    Action,
    Action_Selection,
    Entity,
    Environment,
    Movement_System,
    Observation,
    Position,
    Target_Is_Self,
)
from word_play.presets.entity_orderings import entity_definition_order


@dataclass(slots=True)
class Shared_Room_Position(Position):
    label: str = "shared_room"

    def __str__(self) -> str:
        return self.label


SHARED_ROOM_MOVEMENT_SYSTEM = Movement_System(
    position_type=Shared_Room_Position,
    movement_options=[],
    positions_are_close=lambda _a, _b: True,
)


class Play_Signal(Action):
    def __init__(self, signal_value: int):
        self.signal_value = signal_value
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"signal": self.signal_value}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Play signal {self.signal_value}."


@dataclass(slots=True)
class Private_Sum_Observation(Observation):
    agent_name: str
    teammate_names: list[str]
    step_index: int
    max_steps: int
    signal_modulus: int
    private_signal: int
    last_reward: float
    info: dict

    def __str__(self) -> str:
        if "action_success" not in self.info:
            prev_block = ""
        else:
            status = "succeeded" if self.info["action_success"] else "FAILED"
            details = ""
            step_info = self.info.get("action_info")
            if isinstance(step_info, dict):
                details = (
                    "\nLAST STEP RESULT:"
                    f"\n  team_status: {step_info.get('team_status')}"
                    f"\n  expected_signal: {step_info.get('expected_signal')}"
                    f"\n  team_choices: {step_info.get('choices')}"
                )
            prev_block = f"LAST ACTION: {status}{details}\n\n"

        steps_remaining = max(0, self.max_steps - self.step_index)
        teammates = ", ".join(self.teammate_names)
        communication_summary = self.info.get("communication_summary", {})
        if isinstance(communication_summary, dict):
            received_signals = communication_summary.get("received_signals", {})
            own_signal = communication_summary.get("own_signal", self.private_signal)
            is_complete = communication_summary.get("is_complete")
        else:
            received_signals = {}
            own_signal = self.private_signal
            is_complete = False

        if isinstance(received_signals, dict):
            received_signals_text = ", ".join(
                f"{name}={value}" for name, value in received_signals.items()
            ) or "(none)"
        else:
            received_signals_text = "(none)"

        return "\n\n".join(
            [
                prev_block + f"REWARD THIS TURN: {self.last_reward}",
                "\n".join(
                    [
                        "OBJECTIVE:",
                        "  All agents must play the same correct signal each step.",
                        "  Correct signal rule: (sum of all private signals) mod signal_modulus.",
                        "  Your observation contains only your own private signal.",
                        "  You must communicate to recover the full sum each step.",
                    ]
                ),
                "\n".join(
                    [
                        "CURRENT STATE:",
                        f"  your_name: {self.agent_name}",
                        f"  teammate_names: [{teammates}]",
                        f"  step_index: {self.step_index}/{self.max_steps}",
                        f"  steps_remaining: {steps_remaining}",
                        f"  signal_modulus: {self.signal_modulus}",
                        f"  your_private_signal: {self.private_signal}",
                    ]
                ),
                "\n".join(
                    [
                        "COMMUNICATION SUMMARY (this step):",
                        f"  own_signal: {own_signal}",
                        f"  received_signals: {received_signals_text}",
                        f"  all_teammates_reported: {is_complete}",
                    ]
                ),
                "AVAILABLE ACTIONS:\n"
                + "".join(f"  [{idx}] {action_selection}\n" for idx, action_selection in enumerate(self.possible_actions)).rstrip(),
            ]
        )


def private_sum_reward(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    return env.last_step_rewards.copy()


class Private_Sum_Coordination(Environment):
    def __init__(
        self,
        description: str,
        agents: list[Entity],
        *,
        signal_modulus: int = 5,
        max_steps: int = 40,
    ):
        if len(agents) < 2:
            raise ValueError("Private_Sum_Coordination requires at least two agents.")
        if signal_modulus < 2:
            raise ValueError("signal_modulus must be at least 2.")
        if max_steps <= 0:
            raise ValueError("max_steps must be positive.")

        self.signal_modulus = signal_modulus
        self.max_steps = max_steps
        self.step_index = 0
        self.private_signals: dict[str, int] = {}
        self.expected_team_signal = 0
        self.last_round_choices: dict[str, int] = {}
        self.last_step_rewards: list[float] = [0.0 for _ in agents]
        self._rng = random.Random()

        super().__init__(
            description=description,
            entities=agents,
            movement_system=SHARED_ROOM_MOVEMENT_SYSTEM,
            reward_func=private_sum_reward,
            entity_order=entity_definition_order,
        )

    def _sample_private_signals(self) -> None:
        agent_entities = [entity for entity in self.state.entities if entity.is_agent]
        self.private_signals = {
            entity.name: self._rng.randrange(self.signal_modulus)
            for entity in agent_entities
        }
        self.expected_team_signal = sum(self.private_signals.values()) % self.signal_modulus

    def private_signal_for(self, agent_name: str) -> int:
        return self.private_signals[agent_name]

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        teammates = [other.name for other in self.agents if other is not agent]
        return Private_Sum_Observation(
            possible_actions=self.possible_actions(agent),
            agent_name=agent.name,
            teammate_names=teammates,
            step_index=self.step_index,
            max_steps=self.max_steps,
            signal_modulus=self.signal_modulus,
            private_signal=self.private_signals[agent.name],
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.step_index += 1
        self.last_round_choices = {}
        chosen_signals = []

        for action_selection in action_selections:
            if not isinstance(action_selection.action, Play_Signal):
                raise TypeError("Private_Sum_Coordination only supports Play_Signal actions.")
            signal_value = action_selection.action.signal_value
            self.last_round_choices[action_selection.actor.name] = signal_value
            chosen_signals.append(signal_value)

        all_correct = all(signal == self.expected_team_signal for signal in chosen_signals)
        fully_coordinated = len(set(chosen_signals)) == 1

        if all_correct:
            self.last_step_rewards = [1.0 for _ in self.agents]
            team_status = "correct"
        elif fully_coordinated:
            self.last_step_rewards = [-0.25 for _ in self.agents]
            team_status = "coordinated_but_wrong"
        else:
            self.last_step_rewards = [-0.75 for _ in self.agents]
            team_status = "miscoordinated"

        step_info = {
            "team_status": team_status,
            "expected_signal": self.expected_team_signal,
            "choices": self.last_round_choices.copy(),
            "step_index": self.step_index,
        }
        for info in self.infos:
            info["action_info"] = step_info

        if self.step_index >= self.max_steps:
            self.truncations = [True for _ in self.agents]
            return

        self._sample_private_signals()

    def _reset(self, seed=None) -> None:
        if seed is not None:
            self._rng.seed(seed)
        self.step_index = 0
        self.last_round_choices = {}
        self.last_step_rewards = [0.0 for entity in self.state.entities if entity.is_agent]
        self._sample_private_signals()


def build_private_sum_agents(*policies, signal_modulus: int = 5) -> list[Entity]:
    agents = []
    for idx, policy in enumerate(policies):
        if idx < 26:
            name = f"Agent {chr(ord('A') + idx)}"
        else:
            name = f"Agent {idx + 1}"
        agents.append(
            Entity(
                name=name,
                position=Shared_Room_Position(),
                actions=[Play_Signal(signal_value) for signal_value in range(signal_modulus)],
                components=[policy],
            )
        )
    return agents
