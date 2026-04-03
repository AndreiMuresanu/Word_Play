from __future__ import annotations

from dataclasses import dataclass

from word_play.core import (
    Action_Selection,
    Entity,
    Environment,
    Observation,
)
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.movement.simple_1d_grid import INFINITE_1D_MOVEMENT_SYSTEM, Position_1D
from word_play.presets.movement.simple_2d_grid import Move_Left, Move_Right
from word_play.presets.systems.do_nothing import Do_Nothing


@dataclass(slots=True)
class Line_Tracking_Observation(Observation):
    agent_position: int
    target_position: int
    target_drift_direction: int
    steps_remaining: int
    last_reward: float
    info: dict

    def _direction_text(self, value: int) -> str:
        if value > 0:
            return "right"
        if value < 0:
            return "left"
        return "still"

    def __str__(self) -> str:
        if "action_success" not in self.info:
            prev_block = ""
        else:
            status = "succeeded" if self.info["action_success"] else "FAILED"
            prev_block = f"LAST ACTION: {status}\n\n"

        relative_offset = self.target_position - self.agent_position
        if relative_offset > 0:
            target_side = "right"
        elif relative_offset < 0:
            target_side = "left"
        else:
            target_side = "same position"

        return "\n\n".join(
            [
                prev_block + f"REWARD THIS TURN: {self.last_reward}",
                "\n".join(
                    [
                        "OBJECTIVE:",
                        "  Keep the agent aligned with the moving target.",
                        "  Being on the same position as the target is best.",
                        "  The episode ends if the agent gets too far from the target.",
                    ]
                ),
                "\n".join(
                    [
                        "CURRENT STATE:",
                        f"  agent_position: {self.agent_position}",
                        f"  target_position: {self.target_position}",
                        f"  relative_offset: {relative_offset}",
                        f"  target_side: {target_side}",
                        f"  target_drift_direction: {self._direction_text(self.target_drift_direction)}",
                        f"  steps_remaining: {self.steps_remaining}",
                    ]
                ),
                "\n".join(
                    [
                        "CONTROL HINT:",
                        "  If the target is to your right, moving right usually helps.",
                        "  If the target is to your left, moving left usually helps.",
                        "  If you are already aligned, staying still can be good unless the target is about to drift away.",
                    ]
                ),
                "AVAILABLE ACTIONS:\n"
                + "".join(f"  [{idx}] {action_selection}\n" for idx, action_selection in enumerate(self.possible_actions)).rstrip(),
            ]
        )


def line_tracking_reward(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    current_distance = env.current_distance_to_target
    if current_distance == 0:
        return [1.0]

    if current_distance < env.previous_distance_to_target:
        return [0.25]

    if current_distance > env.previous_distance_to_target:
        return [-0.25]

    return [0.0]


class Line_Tracking_1D(Simple_Env_Reset_Mixin, Environment):
    def __init__(
        self,
        description: str,
        entities: list[Entity],
        *,
        line_min: int = -4,
        line_max: int = 4,
        max_steps: int = 30,
        lose_distance: int = 3,
        target_start: int = 1,
        target_drift_direction: int = 1,
    ):
        self.line_min = line_min
        self.line_max = line_max
        self.max_steps = max_steps
        self.lose_distance = lose_distance
        self.target_start = target_start
        self.initial_target_drift_direction = target_drift_direction
        self.target_position = target_start
        self.target_drift_direction = target_drift_direction
        self.steps_elapsed = 0
        self.previous_distance_to_target = abs(0 - self.target_position)
        self.current_distance_to_target = self.previous_distance_to_target

        super().__init__(
            description,
            entities,
            movement_system=INFINITE_1D_MOVEMENT_SYSTEM,
            reward_func=line_tracking_reward,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id: int) -> Observation:
        return Line_Tracking_Observation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            agent_position=self.agents[agent_id].position.x,
            target_position=self.target_position,
            target_drift_direction=self.target_drift_direction,
            steps_remaining=max(0, self.max_steps - self.steps_elapsed),
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.previous_distance_to_target = abs(self.agents[0].position.x - self.target_position)

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.steps_elapsed += 1
        self.current_distance_to_target = abs(self.agents[0].position.x - self.target_position)

        next_target = self.target_position + self.target_drift_direction
        if next_target < self.line_min or next_target > self.line_max:
            self.target_drift_direction *= -1
            next_target = self.target_position + self.target_drift_direction
        self.target_position = next_target

        agent_position = self.agents[0].position.x
        if agent_position < self.line_min:
            self.agents[0].position.x = self.line_min
        elif agent_position > self.line_max:
            self.agents[0].position.x = self.line_max

        if self.steps_elapsed >= self.max_steps:
            self.truncations[0] = True

    def _reset(self, seed=None) -> None:
        super()._reset(seed=seed)
        self.target_position = self.target_start
        self.target_drift_direction = self.initial_target_drift_direction
        self.steps_elapsed = 0
        agent_entities = [entity for entity in self.state.entities if entity.is_agent]
        self.previous_distance_to_target = abs(agent_entities[0].position.x - self.target_position)
        self.current_distance_to_target = self.previous_distance_to_target


def build_line_tracking_agent(name: str, policy_component) -> Entity:
    return Entity(
        name=name,
        position=Position_1D(0),
        actions=[Move_Left(), Do_Nothing(), Move_Right()],
        components=[policy_component],
    )
