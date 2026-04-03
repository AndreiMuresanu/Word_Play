from __future__ import annotations

from typing import Callable

from word_play.core import Entity, Environment, Observation, Action_Selection
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D
from word_play.presets.observation.simple_observation import Simple_Observation
from word_play.presets.reward_functions import zero_reward_func


# TODO: ANDREI: make this a nice preset, e.g., have the reward_func=zero_reward_func be a default not a fixed thing
class Simple_2D_Grid_World(Simple_Env_Reset_Mixin, Environment):
    def __init__(
        self,
        description: str,
        entities: list[Entity],
        entity_order: Callable[[list[Entity], Environment], list[int]] = entity_definition_order,
        observation_radius: int = 0,
    ):
        self.observation_radius = observation_radius
        super().__init__(
            description,
            entities,
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=zero_reward_func,
            entity_order=entity_order,
        )

    def entities_in_observation_square(self, position: Position_2D) -> list[Entity]:
        return [
            entity
            for entity in self.state.entities
            if abs(entity.position.x - position.x) <= self.observation_radius
            and abs(entity.position.y - position.y) <= self.observation_radius
        ]

    def observe(self, agent_id: int) -> Observation:
        return Simple_Observation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            nearby_entities=self.entities_in_observation_square(self.agents[agent_id].position),
            agent=self.agents[agent_id],
            last_reward=self.last_rewards[agent_id],
            info=self.infos[agent_id],
            observation_radius=self.observation_radius,
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]):
        pass

    def environment_end_of_step(self, action_selections: list[Action_Selection]):
        pass
