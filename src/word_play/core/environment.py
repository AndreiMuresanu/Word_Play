from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from .actions import Action_Selection, Target_Is_Nearby, Target_Is_Self, Target_Not_Self
from .components import Non_Agent_Policy
from .entity import Entity
from .movement import Movement_System, Position
from .observation import Observation
from .rendering import Render_Result, Renderer, Renderer_State


@dataclass(slots=True)
class Environment_State:
    """
    Environments can inherit from the this class to track more complex states.

    The order of the entity list defines the order in which their step functions and actions execute.
    """

    entities: list[Entity]
    renderer_state: Renderer_State = field(default_factory=Renderer_State)


# TODO: need to make agent_id more general then an int. This way we can make a general last() method which returns
# 	a dict indexed by agent_id. You can imagine the usage being: a user loads an env and now instantly knows what
# 	agents they are controlling. Need to likely scope this better.
class Environment(ABC):
    """
    The Environment object represents the entire simulation.

    Assumptions:
        - New agents will not be added to the Environment after initialization. However, agents can be delete (e.g.,
          if an agent dies). And new non-agent entities can be added.

    Info:
        - Agent actions are collected simultaneously and their execution and conflict resolution according to the
          Agent Environment Cycle (AEC) protocol. E.g., all entities (including agents) have a specified turn order
          (this turn order could be random) and actions are executed sequentially in accordance to this entity
          ordering. For example, if two agents both select to pick up the same object, then only the first agent
          will pick up the object and the second agent's action will fail resulting in no action for the second
          agent. If desired, the Environment class can be inherited from and edited to allow for custom conflict
          resolution system (e.g., if both agents try to pick up the same object, neither of their actions succeed
          and they both receive a penalty). Alternatively, agents also implement this type of logic for specific
          actions using custom actions and a custom conflict resolution component.
    """

    def __init__(
        self,
        description: str,
        entities: list[Entity],
        movement_system: Movement_System,
        reward_func: Callable[[list[Action_Selection, Environment]], list[float]],
        entity_order: Callable[[list[Entity], Environment], list[int]],
        renderer: Renderer | None = None,
    ) -> None:
        """
        entity_order defines how the ordering of state.entities is changed each step. The order of state.entities
        defines the order in which entity actions and steps are executed.

        NOTE: The entity_order function receives as input a **shallow** copy of the environment's entity list and a
              reference to the environment. It returns a list representing the new indices of the entity list. It may
              view, but *not* modify the entity list it is given. The environment is given to allow for very flexible
              reordering rules. E.g., reordering based on an entity's initiative stat.
        """
        self.description = description
        self.renderer = renderer
        self.state = Environment_State(entities, renderer_state=self._create_renderer_state())
        self.cur_step = 0
        self.movement_system = movement_system
        self.reward_func = reward_func
        self.entity_order = entity_order
        self.reset()
        self.post_init()

    def _create_renderer_state(self) -> Renderer_State:
        if self.renderer is None:
            return Renderer_State()
        return self.renderer.create_renderer_state()

    @property
    def render_state(self) -> Renderer_State:
        return self.state.renderer_state

    def post_init(self) -> None:
        """This method is called at the end of the __init__ method. It can be overwritten to provide more complex logic."""
        pass

    @abstractmethod
    def observe(self, agent_id: int) -> Observation:
        pass

    @abstractmethod
    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        """
        This is where you define environment instance specific things you want happening happening at the start of each step.
        Example:
            - you want to have countdown timer
            - you want your environment to switch between day and night
            - you want to have random events occurs with some probability each day
            - etc.
        """
        pass

    @abstractmethod
    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        """
        This is where you define environment instance specific things you want happening happening at the end of each step.
        Example:
            - you want to have countdown timer
            - you want your environment to switch between day and night
            - you want to have random events occurs with some probability each day
            - etc.
        """
        pass

    @abstractmethod
    def _reset(self, seed=None) -> None:
        """This method is used by the reset() method to reset environment specific state."""
        pass

    def render(self) -> Render_Result:
        """Render via the environment's optional active renderer."""
        if self.renderer is None:
            raise NotImplementedError("This environment does not support rendering.")
        result = self.renderer.render(self)
        self.render_state.clear_events()
        return result

    def reset(self, seed=None) -> None:
        self.cur_episode_seed = seed
        self._reset(seed=seed)
        self.state.renderer_state = self._create_renderer_state()
        self.cur_step = 0
        self._init_agent_list()
        self._init_agent_idx_dict()
        self.last_rewards = [None] * len(self.agents)
        self.terminations = [False] * len(self.agents)
        self.truncations = [False] * len(self.agents)
        self.infos = [{} for _ in self.agents]

        self._reorder_entities()

        # We iterate over a copy since an entity may instantiate another entity during its on_instantiation. If that
        # happens then not using a copy results in the new entity's on_instantiation method being called twice
        for entity in self.state.entities.copy():
            entity.on_instantiation(env=self, seed=seed)

    def _init_agent_list(self) -> None:
        # Note that this does not duplicate the agent entities. We are simply storing references to the agent objects
        self.agents = [entity for entity in self.state.entities if entity.is_agent]

    def _init_agent_idx_dict(self) -> None:
        self.agent_to_idx = {agent: i for i, agent in enumerate(self.agents)}

    def _reorder_entities(self) -> None:
        new_order = self.entity_order(self.state.entities.copy(), self)
        self.state.entities[:] = [self.state.entities[i] for i in new_order]

    def _perform_action(self, action_selection: Action_Selection) -> tuple[bool, dict | None]:
        """
        Returns a tuple[bool, dict | None].

        The bool indicates whether the action was successful. Due to simultaneous AEC-style action selection, actions
        may be invalid by the time they are executed. E.g., if two agents request to pick up the same object, only the
        first actions request will be valid.

        The dict, if present, returns any additional information returned by the action.
        """
        action_success = False
        action_info = None
        if action_selection.action.is_valid(
            action_selection.actor, action_selection.target_entity, self, kwargs=action_selection.action_kwargs
        ):
            action_info = action_selection.action(
                action_selection.actor, action_selection.target_entity, self, action_selection.action_kwargs
            )
            action_success = True

        return action_success, action_info

    def step(self, action_selections: list[Action_Selection]) -> None:
        assert len(self.agents) == len(action_selections), (
            "All agents must submit an action. Agents who have reached terminal "
            "states may not submit actions. "
            f"Expected {len(self.agents)} actions, "
            f"but received {len(action_selections)}."
        )
        agent_to_action_selection = {
            agent: action_selection for agent, action_selection in zip(self.agents, action_selections)
        }

        self.environment_start_of_step(action_selections)

        for entity in self.state.entities:
            entity.pre_actions_step(env=self)

        for entity in self.state.entities:
            if entity.is_agent:
                action_selection = agent_to_action_selection[entity]
                action_success, action_info = self._perform_action(action_selection)
                agent_index = self.agent_to_idx[action_selection.actor]
                self.infos[agent_index]["action_success"] = action_success
                self.infos[agent_index]["action_info"] = action_info
            elif entity.has_component(Non_Agent_Policy):
                possible_actions = self.possible_actions(entity)
                action_selection = entity.get_component(Non_Agent_Policy).select_action(
                    possible_actions=possible_actions, env=self
                )
                self._perform_action(action_selection)

        for entity in self.state.entities:
            entity.post_actions_step(env=self)

        self.environment_end_of_step(action_selections)

        self.last_rewards = self.reward_func(action_selections, self)
        self.cur_step += 1
        self._reorder_entities()

    def last(self, agent_id: int) -> tuple[Observation, float, bool, bool, dict]:
        """
        Returns:
        - observation
        - instantaneous reward
        - terminatation status: has the agent reached a terminal state in the MDP?
        - truncatation status: has the episode ended due to a reason outside of the scope of the MDP (ex., time limit)?
        - info

        for the current agent.
        """
        return (
            self.observe(agent_id),
            self.last_rewards[agent_id],
            self.terminations[agent_id],
            self.truncations[agent_id],
            self.infos[agent_id],
        )

    def entities_near_position(self, position: Position) -> list[Entity]:
        return [
            entity
            for entity in self.state.entities
            if self.movement_system.positions_are_close(position, entity.position)
        ]

    # TODO: it is possible to generalize this filtering based on Action_Validation logic to a general entity query
    #       system. Doing so would allow extensions to the environment (e.g., new components) to also benefit from these
    #       optimizations. These optimizations can be quite extreme, e.g., we could maintain a hashmap mapping positions
    #       to lists of nearby entities. However, the main bottleneck of the simulation will always be LLM calls in the
    #       policy, thus, these optimizations don't make a big difference (searching over 1mil entities is still very
    #       fast).
    def possible_actions(self, entity: Entity) -> list[Action_Selection]:
        nearby_entities = [nearby_entity for nearby_entity in self.entities_near_position(entity.position)]
        possible_actions = []

        for action in entity.actions:
            if any(isinstance(rule, Target_Is_Self) for rule in action.validation_rules):
                possible_targets = [entity]
            elif any(isinstance(rule, Target_Is_Nearby) for rule in action.validation_rules):
                possible_targets = nearby_entities.copy()
            else:
                possible_targets = self.state.entities

            if any(isinstance(rule, Target_Not_Self) for rule in action.validation_rules):
                possible_targets.remove(entity)

            possible_actions += [
                Action_Selection(action=action, action_kwargs=None, actor=entity, target_entity=target, env=self)
                for target in possible_targets
                if action.is_valid(entity, target, self)
            ]

        return possible_actions

    def instantiate_entity(self, entity: Entity, entity_order_position: int | None = None):
        """
        entity_order_position defined the position within the entity list that the new entity is added. This order
        defines the execution order of actions and steps. By default we add new entity to the end of the list.
        """
        if entity.is_agent:
            raise ValueError("All agents must be added when the environment is initialized.")

        if entity_order_position:
            self.state.entities.insert(entity_order_position, entity)
        else:
            self.state.entities.append(entity)

        entity.on_instantiation(env=self, seed=self.cur_episode_seed)

    def destroy_entity(self, entity: Entity):
        entity.on_destroy(env=self)
        self.state.entities.remove(entity)
        if entity.is_agent:
            self.terminations[self.agent_to_idx[entity]] = True
            self.agents.remove(entity)
            del self.agent_to_idx[entity]
