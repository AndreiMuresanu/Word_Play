from __future__ import annotations

import math
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
class CartPole_Position(Position):
    label: str = "cart_pole"

    def __str__(self):
        return self.label


CART_POLE_MOVEMENT_SYSTEM = Movement_System(
    position_type=CartPole_Position,
    movement_options=[],
    positions_are_close=lambda _a, _b: True,
)


class Push_Left(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"force_direction": -1}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Push cart left."


class Push_Right(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"force_direction": 1}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Push cart right."


@dataclass(slots=True)
class CartPole_Observation(Observation):
    x: float
    x_dot: float
    theta: float
    theta_dot: float
    last_reward: float
    info: dict

    def _direction_label(self, value: float, threshold: float = 1e-3) -> str:
        if value > threshold:
            return "right"
        if value < -threshold:
            return "left"
        return "centered"

    def __str__(self) -> str:
        if "action_success" not in self.info:
            prev_block = ""
        else:
            status = "succeeded" if self.info["action_success"] else "FAILED"
            prev_block = f"LAST ACTION: {status}\n\n"

        pole_lean = self._direction_label(self.theta)
        pole_fall = self._direction_label(self.theta_dot)
        cart_drift = self._direction_label(self.x_dot)

        state_block = "\n".join(
            [
                "CURRENT STATE:",
                f"  cart_position: {self.x:.4f}",
                f"  cart_velocity: {self.x_dot:.4f}",
                f"  pole_angle_rad: {self.theta:.4f}",
                f"  pole_angle_deg: {math.degrees(self.theta):.2f}",
                f"  pole_angular_velocity: {self.theta_dot:.4f}",
            ]
        )
        interpretation_block = "\n".join(
            [
                "STATE INTERPRETATION:",
                f"  pole lean direction: {pole_lean}",
                f"  pole falling direction: {pole_fall}",
                f"  cart drift direction: {cart_drift}",
            ]
        )
        objective_block = "\n".join(
            [
                "OBJECTIVE:",
                "  Keep the pole balanced for as many steps as possible.",
                "  The episode ends if |cart_position| > 2.4 or |pole_angle_deg| > 12.",
            ]
        )
        control_hint_block = "\n".join(
            [
                "CONTROL HINT:",
                "  If the pole leans right, pushing right often helps move the cart under it.",
                "  If the pole leans left, pushing left often helps move the cart under it.",
                "  Pole angular velocity tells you whether it is continuing to fall in that direction.",
            ]
        )
        actions_block = "AVAILABLE ACTIONS:\n" + "".join(
            f"  [{idx}] {action_selection}\n" for idx, action_selection in enumerate(self.possible_actions)
        ).rstrip()

        return "\n\n".join(
            [
                prev_block + f"REWARD THIS TURN: {self.last_reward}",
                objective_block,
                state_block,
                interpretation_block,
                control_hint_block,
                actions_block,
            ]
        )


def cart_pole_reward(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    env = env
    return [0.0 if env.terminations[0] else 1.0]


class Cart_Pole(Environment):
    gravity = 9.8
    masscart = 1.0
    masspole = 0.1
    total_mass = masscart + masspole
    length = 0.5
    polemass_length = masspole * length
    force_mag = 10.0
    tau = 0.02
    theta_threshold_radians = 12 * 2 * math.pi / 360
    x_threshold = 2.4

    def __init__(self, description: str, agent: Entity):
        self._rng = random.Random()
        self.x = 0.0
        self.x_dot = 0.0
        self.theta = 0.0
        self.theta_dot = 0.0
        super().__init__(
            description=description,
            entities=[agent],
            movement_system=CART_POLE_MOVEMENT_SYSTEM,
            reward_func=cart_pole_reward,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id: int) -> Observation:
        return CartPole_Observation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            x=self.x,
            x_dot=self.x_dot,
            theta=self.theta,
            theta_dot=self.theta_dot,
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        if not action_selections:
            return

        selected_action = action_selections[0].action
        force = -self.force_mag if isinstance(selected_action, Push_Left) else self.force_mag

        costheta = math.cos(self.theta)
        sintheta = math.sin(self.theta)

        temp = (force + self.polemass_length * self.theta_dot**2 * sintheta) / self.total_mass
        thetaacc = (self.gravity * sintheta - costheta * temp) / (
            self.length * (4.0 / 3.0 - self.masspole * costheta**2 / self.total_mass)
        )
        xacc = temp - self.polemass_length * thetaacc * costheta / self.total_mass

        self.x = self.x + self.tau * self.x_dot
        self.x_dot = self.x_dot + self.tau * xacc
        self.theta = self.theta + self.tau * self.theta_dot
        self.theta_dot = self.theta_dot + self.tau * thetaacc

        terminated = bool(
            self.x < -self.x_threshold
            or self.x > self.x_threshold
            or self.theta < -self.theta_threshold_radians
            or self.theta > self.theta_threshold_radians
        )
        self.terminations[0] = terminated

    def _reset(self, seed=None) -> None:
        if seed is not None:
            self._rng.seed(seed)

        self.x = self._rng.uniform(-0.05, 0.05)
        self.x_dot = self._rng.uniform(-0.05, 0.05)
        self.theta = self._rng.uniform(-0.05, 0.05)
        self.theta_dot = self._rng.uniform(-0.05, 0.05)
