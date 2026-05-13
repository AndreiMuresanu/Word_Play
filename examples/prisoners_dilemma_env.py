from __future__ import annotations

from word_play.core import (
    Action,
    Action_Selection,
    Entity,
    Environment,
    Observation,
    Target_Is_Self,
)
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.movement.single_point import (
    SINGLE_POINT_MOVEMENT_SYSTEM,
    Single_Point_Position,
)
from word_play.presets.observation.simple_observation import Simple_Observation


Prisoners_Dilemma_Position = Single_Point_Position


class Cooperate(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"choice": "cooperate"}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Cooperate."


class Defect(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return {"choice": "defect"}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Defect."


def prisoners_dilemma_reward(agent_actions: list[Action_Selection], env: Environment) -> list[float]:
    return env.last_step_rewards.copy()


class Prisoners_Dilemma(Simple_Env_Reset_Mixin, Environment):
    def __init__(
        self,
        description: str,
        agents: list[Entity],
        *,
        max_rounds: int = 40,
        mutual_cooperate_reward: float = 3.0,
        temptation_reward: float = 5.0,
        mutual_defect_reward: float = 1.0,
        sucker_reward: float = 0.0,
    ):
        if len(agents) != 2:
            raise ValueError("Prisoners_Dilemma requires exactly two agents.")
        if max_rounds <= 0:
            raise ValueError("max_rounds must be positive.")
        if not (temptation_reward > mutual_cooperate_reward > mutual_defect_reward > sucker_reward):
            raise ValueError(
                "Expected Prisoner's Dilemma payoff ordering: "
                "temptation > mutual_cooperate > mutual_defect > sucker."
            )

        self.max_rounds = max_rounds
        self.mutual_cooperate_reward = mutual_cooperate_reward
        self.temptation_reward = temptation_reward
        self.mutual_defect_reward = mutual_defect_reward
        self.sucker_reward = sucker_reward

        self.round_index = 0
        self.last_round_choices: dict[str, str] = {}
        self.last_joint_profile: str | None = None
        self.last_step_rewards: list[float] = [0.0 for _ in agents]
        self.cumulative_rewards: list[float] = [0.0 for _ in agents]

        super().__init__(
            description=description,
            entities=agents,
            movement_system=SINGLE_POINT_MOVEMENT_SYSTEM,
            reward_func=prisoners_dilemma_reward,
            entity_order=entity_definition_order,
        )

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        opponent = self.agents[1 - agent_id]
        rounds_remaining = max(0, self.max_rounds - self.round_index)

        extra_sections = (
            "\n".join(
                [
                    "OBJECTIVE:",
                    "  Choose Cooperate or Defect each round.",
                    "  Maximize your own cumulative reward across repeated rounds.",
                    "  Your opponent chooses at the same time, so you cannot react within the current round.",
                ]
            ),
            "\n".join(
                [
                    "CURRENT STATE:",
                    f"  your_name: {agent.name}",
                    f"  opponent_name: {opponent.name}",
                    f"  round: {self.round_index}/{self.max_rounds}",
                    f"  rounds_remaining: {rounds_remaining}",
                    f"  your_cumulative_reward: {self.cumulative_rewards[agent_id]:+.2f}",
                ]
            ),
            "\n".join(
                [
                    "PAYOFFS:",
                    "  If both cooperate: "
                    f"you={self.mutual_cooperate_reward:+.2f}, opponent={self.mutual_cooperate_reward:+.2f}",
                    "  If you defect and opponent cooperates: "
                    f"you={self.temptation_reward:+.2f}, opponent={self.sucker_reward:+.2f}",
                    "  If you cooperate and opponent defects: "
                    f"you={self.sucker_reward:+.2f}, opponent={self.temptation_reward:+.2f}",
                    "  If both defect: "
                    f"you={self.mutual_defect_reward:+.2f}, opponent={self.mutual_defect_reward:+.2f}",
                ]
            ),
        )

        return Simple_Observation(
            possible_actions=self.possible_actions(agent),
            nearby_entities=self.entities_near_position(agent.position),
            agent=agent,
            last_reward=0.0 if self.last_rewards[agent_id] is None else self.last_rewards[agent_id],
            info=self.infos[agent_id],
            observation_radius=0,
            extra_sections=extra_sections,
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.last_round_choices = {}
        choices_in_order: list[str] = []

        for action_selection in action_selections:
            if isinstance(action_selection.action, Cooperate):
                choice = "cooperate"
            elif isinstance(action_selection.action, Defect):
                choice = "defect"
            else:
                raise TypeError("Prisoners_Dilemma only supports Cooperate and Defect actions.")

            self.last_round_choices[action_selection.actor.name] = choice
            choices_in_order.append(choice)

        first_choice, second_choice = choices_in_order
        if first_choice == "cooperate" and second_choice == "cooperate":
            rewards = [self.mutual_cooperate_reward, self.mutual_cooperate_reward]
            joint_profile = "cooperate/cooperate"
        elif first_choice == "defect" and second_choice == "cooperate":
            rewards = [self.temptation_reward, self.sucker_reward]
            joint_profile = "defect/cooperate"
        elif first_choice == "cooperate" and second_choice == "defect":
            rewards = [self.sucker_reward, self.temptation_reward]
            joint_profile = "cooperate/defect"
        else:
            rewards = [self.mutual_defect_reward, self.mutual_defect_reward]
            joint_profile = "defect/defect"

        self.last_step_rewards = rewards
        self.cumulative_rewards = [
            cumulative + reward
            for cumulative, reward in zip(self.cumulative_rewards, rewards)
        ]
        self.last_joint_profile = joint_profile
        self.round_index += 1

        round_info = {
            "round_index": self.round_index,
            "joint_profile": joint_profile,
            "choices": self.last_round_choices.copy(),
            "rewards": {
                agent.name: reward
                for agent, reward in zip(self.agents, rewards)
            },
            "cumulative_rewards": {
                agent.name: reward
                for agent, reward in zip(self.agents, self.cumulative_rewards)
            },
        }
        for info in self.infos:
            info["action_info"] = round_info

        if self.round_index >= self.max_rounds:
            self.truncations = [True for _ in self.agents]

    def _reset(self, seed=None) -> None:
        super()._reset(seed=seed)
        agent_count = len([entity for entity in self.state.entities if entity.is_agent])
        self.round_index = 0
        self.last_round_choices = {}
        self.last_joint_profile = None
        self.last_step_rewards = [0.0 for _ in range(agent_count)]
        self.cumulative_rewards = [0.0 for _ in range(agent_count)]


def build_prisoners_dilemma_agents(*policies) -> list[Entity]:
    if len(policies) != 2:
        raise ValueError("build_prisoners_dilemma_agents requires exactly two policies.")

    agents = []
    for idx, policy in enumerate(policies):
        agents.append(
            Entity(
                name=f"Agent {chr(ord('A') + idx)}",
                position=Prisoners_Dilemma_Position(),
                actions=[Cooperate(), Defect()],
                components=[policy],
            )
        )
    return agents
