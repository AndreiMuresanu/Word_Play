from __future__ import annotations

import random
from dataclasses import dataclass

from word_play.core import Action, Action_Selection, Entity, Environment, Movement_System, Observation, Position, Target_Is_Self
from word_play.presets.entity_orderings import entity_definition_order


@dataclass(slots=True)
class Boat_Position(Position):
    label: str = "boat"

    def __str__(self) -> str:
        return self.label


BOAT_MOVEMENT_SYSTEM = Movement_System(
    position_type=Boat_Position,
    movement_options=[],
    positions_are_close=lambda _a, _b: True,
)


class Paddle(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"choice": "paddle"}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Paddle."


class Wait(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"choice": "wait"}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Wait."


@dataclass(slots=True)
class Boat_Race_Observation(Observation):
    agent_name: str
    partner_name: str
    race_index: int
    total_races: int
    race_step: int
    race_duration: int
    boat_progress: int
    goal_progress: int
    consecutive_coordinated_paddles: int
    private_wait_steps: int | None
    is_informed_agent: bool
    last_reward: float
    info: dict

    def __str__(self) -> str:
        if "action_success" not in self.info:
            prev_block = ""
        else:
            status = "succeeded" if self.info["action_success"] else "FAILED"
            details = ""
            if self.info.get("action_info"):
                details = f"\nLAST STEP INFO: {self.info['action_info']}"
            prev_block = f"LAST ACTION: {status}{details}\n\n"

        steps_remaining = max(0, self.race_duration - self.race_step)
        private_block = (
            "\n".join(
                [
                    "PRIVATE INFO:",
                    "  You are the informed rower.",
                    f"  For this race, both rowers should wait {self.private_wait_steps} step(s) before starting to paddle.",
                    "  Tell your partner.",
                ]
            )
            if self.is_informed_agent
            else "\n".join(
                [
                    "PRIVATE INFO:",
                    "  You do not know the correct start timing for this race.",
                    "  Use communication to learn the plan from your partner.",
                ]
            )
        )

        return "\n\n".join(
            [
                prev_block + f"REWARD THIS TURN: {self.last_reward}",
                "\n".join(
                    [
                        "OBJECTIVE:",
                        "  Reach the far shore before the race timer ends.",
                        "  After the correct waiting period, both rowers should paddle together.",
                        "  Three synchronized paddle steps move the boat forward by one space.",
                        "  Incorrect coordination wastes time and can push progress backward.",
                    ]
                ),
                "\n".join(
                    [
                        "CURRENT STATE:",
                        f"  your_name: {self.agent_name}",
                        f"  partner_name: {self.partner_name}",
                        f"  race_index: {self.race_index + 1}/{self.total_races}",
                        f"  race_step: {self.race_step}/{self.race_duration}",
                        f"  steps_remaining_in_race: {steps_remaining}",
                        f"  boat_progress: {self.boat_progress}/{self.goal_progress}",
                        f"  consecutive_coordinated_paddles: {self.consecutive_coordinated_paddles}",
                    ]
                ),
                private_block,
                "AVAILABLE ACTIONS:\n"
                + "".join(f"  [{idx}] {action_selection}\n" for idx, action_selection in enumerate(self.possible_actions)).rstrip(),
            ]
        )


def boat_race_reward(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    return env.last_step_rewards.copy()


class Boat_Race(Environment):
    def __init__(
        self,
        description: str,
        agents: list[Entity],
        *,
        goal_progress: int = 4,
        race_duration: int = 18,
        total_races: int = 8,
    ):
        self.goal_progress = goal_progress
        self.race_duration = race_duration
        self.total_races = total_races

        self.current_race_index = 0
        self.race_step = 0
        self.boat_progress = 0
        self.consecutive_coordinated_paddles = 0
        self.reached_goal = False
        self.failed = False
        self.last_round_choices: dict[str, str] = {}
        self.last_step_rewards: list[float] = [0.0 for _ in agents]
        self.required_wait_steps = 0
        self.informed_agent_name = agents[0].name
        self._rng = random.Random()

        super().__init__(
            description=description,
            entities=agents,
            movement_system=BOAT_MOVEMENT_SYSTEM,
            reward_func=boat_race_reward,
            entity_order=entity_definition_order,
        )
        self._sample_race_setup()

    def _sample_race_setup(self) -> None:
        self.required_wait_steps = self._rng.choice([0, 1])
        agent_entities = [entity for entity in self.state.entities if entity.is_agent]
        self.informed_agent_name = agent_entities[self.current_race_index % len(agent_entities)].name

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        partner = next(other for other in self.agents if other is not agent)
        is_informed_agent = agent.name == self.informed_agent_name
        return Boat_Race_Observation(
            possible_actions=self.possible_actions(agent),
            agent_name=agent.name,
            partner_name=partner.name,
            race_index=self.current_race_index,
            total_races=self.total_races,
            race_step=self.race_step,
            race_duration=self.race_duration,
            boat_progress=self.boat_progress,
            goal_progress=self.goal_progress,
            consecutive_coordinated_paddles=self.consecutive_coordinated_paddles,
            private_wait_steps=self.required_wait_steps if is_informed_agent else None,
            is_informed_agent=is_informed_agent,
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.race_step += 1
        self.last_step_rewards = [0.0 for _ in self.agents]
        self.last_round_choices = {
            action_selection.actor.name: type(action_selection.action).__name__.lower()
            for action_selection in action_selections
        }

        choices_in_order = [self.last_round_choices[agent.name] for agent in self.agents]
        expected_choice = "wait" if self.race_step <= self.required_wait_steps else "paddle"

        if all(choice == expected_choice for choice in choices_in_order):
            self.last_step_rewards = [reward + 0.25 for reward in self.last_step_rewards]
            if expected_choice == "paddle":
                self.consecutive_coordinated_paddles += 1
                if self.consecutive_coordinated_paddles >= 3:
                    self.boat_progress += 1
                    self.last_step_rewards = [reward + 1.0 for reward in self.last_step_rewards]
                    self.consecutive_coordinated_paddles = 0
            else:
                self.consecutive_coordinated_paddles = 0
        else:
            self.consecutive_coordinated_paddles = 0
            self.last_step_rewards = [reward - 0.25 for reward in self.last_step_rewards]
            self.boat_progress = max(0, self.boat_progress - 1)

        step_info = {
            "choices": self.last_round_choices.copy(),
            "boat_progress": self.boat_progress,
            "goal_progress": self.goal_progress,
            "race_index": self.current_race_index + 1,
            "race_step": self.race_step,
        }

        if self.boat_progress >= self.goal_progress:
            self.last_step_rewards = [reward + 1.0 for reward in self.last_step_rewards]
            step_info["race_outcome"] = "finished"
            self._advance_to_next_race_or_end(success=True)
        elif self.race_step >= self.race_duration:
            self.last_step_rewards = [reward - 1.0 for reward in self.last_step_rewards]
            step_info["race_outcome"] = "failed"
            self.failed = True
            self.terminations = [True for _ in self.agents]
        else:
            step_info["race_outcome"] = "ongoing"

        for info in self.infos:
            info["action_info"] = step_info

    def _advance_to_next_race_or_end(self, success: bool) -> None:
        if not success:
            return

        if self.current_race_index + 1 >= self.total_races:
            self.reached_goal = True
            self.terminations = [True for _ in self.agents]
            return

        self.current_race_index += 1
        self.race_step = 0
        self.boat_progress = 0
        self.consecutive_coordinated_paddles = 0
        self._sample_race_setup()

    def _reset(self, seed=None) -> None:
        if seed is not None:
            self._rng.seed(seed)
        self.current_race_index = 0
        self.race_step = 0
        self.boat_progress = 0
        self.consecutive_coordinated_paddles = 0
        self.reached_goal = False
        self.failed = False
        self.last_round_choices = {}
        self.last_step_rewards = [0.0 for entity in self.state.entities if entity.is_agent]
        self._sample_race_setup()


def build_boat_race_agents(*policies) -> list[Entity]:
    names = ["Rower A", "Rower B", "Rower C", "Rower D"]
    agents = []
    for idx, policy in enumerate(policies):
        agents.append(
            Entity(
                name=names[idx],
                position=Boat_Position(),
                actions=[Paddle(), Wait()],
                components=[policy],
            )
        )
    return agents
