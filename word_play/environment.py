from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NamedTuple, Callable, Optional
from enum import Enum


# ---------------------------------------- Movement System Definition ----------------------------------------

# TODO: do we need to add an abstract __eq__ method? tbd as needs arise
@dataclass
class Position(ABC):
	# We keep Position as an ABC with no assumption because environments may have non-coordinate based positions.
	# For example, consider the enum based location-wise (ie., graph-based) positions: 'market', 'office', 'home', etc.
	# additionally, position comparison functions (ex., '>') may be useful
	@abstractmethod
	def __str__(self):
		pass


# TODO: need to check that position_type is being validated in a nice way
# TODO: maybe this can be made simpler and more effecient (we can likely sacrifice some generality)
@dataclass
class Movement_System:
	position_type: Position
	movement_options: list[Action_On_Self]
	positions_are_close: Callable[[Position, Position], bool]
	movement_is_valid: Callable[[Position, Action_On_Self, Environment], bool]


# ---------------------------------------- Action Definition ----------------------------------------

# TODO: would be nice to support actions with additional custom input params. For example, Move_To_Location(location) is
# 		otherwise awkward to implement.
# TODO: might be nice to actions return some kinda of value in order to communicate success/failure/info back to env/agent.
#		For example, if the action is to roll a dice, you need to know what number you rolled.
# TODO: implementing Action using a class might not be the nicest approach. It might be nicer to user a dataclass or namedtuple.
#		Maybe we can replace the Action ABC with a protocol?
# TODO: maybe action should have a can_perform_action(actor) method? This might make it nice to check for action validity
class Action(ABC):
	@staticmethod
	@abstractmethod
	def action_description_text(target_entity: Entity) -> str:
		pass

class Action_On_Other_Entity(ABC):
	@staticmethod
	@abstractmethod
	def __call__(target_entity: Entity, actor: Entity, env: Environment):
		pass

class Action_On_Self(ABC):
	@staticmethod
	@abstractmethod
	def __call__(target_entity: Entity, env: Environment):
		pass


class Action_Selection(NamedTuple):
	action: Action
	target_entity: Entity

	def __str__(self) -> str:
		return self.action.action_description_text(self.target_entity)

# ---------------------------------------- Observation Definition ----------------------------------------

# TODO: we might want to have this be a subclass of Observation named EntityObservation
#	in order to perserve the ability for people to create fully customizable and minimal envs
# NOTE: We delibrately exclude a default __str__ method to force env creators to think about it
#	(We may rethink this decision at some point)
@dataclass
class Observation(ABC):
	possible_actions: list[Action_Selection]

	@abstractmethod
	def __str__(self):
		pass


# ---------------------------------------- Entity Definition ----------------------------------------

@dataclass
class Entity_Properties:
	'''Entities can inherit from the this class to track more complex properties.'''
	name: str

@dataclass
class Entity_State:
	'''Entities can inherit from the this class to track more complex states.'''
	position: Position


# TODO: what are the abstract methods? I dont think there are any
class Entity(ABC):

	# TODO: I think a dataclass with some immutable attributes (the actions) would be a good implementation,
	# however, python does not allow for this. We may still be able to implement this in a nicer way.
	# Options:
	#	- create a custom dataclass decorator with field level freezability
	#	- others?
	# Issues:
	#	- exposed_actions type is not enforced
	#	- init is kinda redundant
	#	- no real abstract methods, thus poor argument for the need of an ABC
	# Comments:
	#	- we don't really need get_all_exposed_action_descriptions() to be in the class def
	@property
	@abstractmethod
	def exposed_actions(self):
		'''
		These are all actions which Agents can perform on this Entity.
		This must be of type: tuple[Action_On_Other_Entity]
		'''
		pass

	def __init__(self, state: Entity_State, properties: Entity_Properties) -> None:
		self.state = state
		self.properties = properties

	# TODO: if we want this method to be very expressive, we can pass the Environment to it as input
	#	Might not be great tho, since it makes Entities less environment agnostic
	@abstractmethod
	def step(self, env: Environment) -> None:
		'''
		This is for logic which happens each step (NOT ACTION SELECTION) and is not handled by Environment.environment_step().
		If no additional logic is needed this function can do nothing.
		Examples:
			- A food entity has a p% chance to rot every step
			- An entity's thirst property decreases by 1 each step
			- etc.
		'''
		pass

	def get_all_exposed_action_descriptions(self):
		return [action.action_description_text(self) for action in self.exposed_actions]


# ---------------------------------------- Agent Definition ----------------------------------------

# TODO: if we want to support minimal/fully extendible Environments then we should rename this to EntityAgent
class Agent(Entity):

	@property
	@abstractmethod
	def actions_on_self(self):
		'''This must be of type: tuple[Action_On_Self]'''
		pass

	# TODO: it might be nice to give the agent access the environment since it is presumable there will be multiple
	# 		"cheater" agents needed for experiments. And we should likely still be able to trust agent creators????
	# TODO: maybe we should make a subclass of Agent which cannot access the environment, and this is what agent creators use
	@abstractmethod
	def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
		'''
		Observation contains a list of all possible actions the agent can take.
		Returns: An Action_Selection and a dictionary of additional information.
		'''
		pass

	# TODO: maybe the env creator defines the agent class and the agent "creator" only defines the select_action method?
	# 	This might make it easier to define certain step functions.
	@abstractmethod
	def step(self) -> None:
		'''
		We override Entity.step() to remove the ability for Agents to pass in the environment as an argument.
		If an Agent wants to access the environment, it should be done through an Action_On_Self.
		'''
		pass


# ---------------------------------------- Environment Definition ----------------------------------------

@dataclass
class Environment_Properties:
	'''Environments can inherit from the this class to track more complex properties.'''
	description: str

@dataclass
class Environment_State:
	'''
	Environments can inherit from the this class to track more complex states.
	
	By default, the order of the entity list defines the order in which their step functions run.
	However, this can be changed by setting the step_execution_order property when initializing the Environment.
	'''
	entities: list[Entity]


# TODO: Is it overkill to have this as an enum or should it just be a string?
class Step_Execution_Order(Enum):
	'''This is used to define the order in which the Environment executes Entity steps and actions.'''
	Entity_Definition_Order = 1	# This is the order in which the entities are defined in the Environment_State
	Agents_First = 2
	Agents_Last = 3


# TODO: Terminations and truncations are currently unsused.
# TODO: need to make agent_id more general then an int. This way we can make a general last() method which returns
# 	a dict of indexed by agent_id. You can imagine the usage being: a user loads an env and now instantly knows what
# 	agents they are controlling. Need to likely scope this better.
class Environment(ABC):

	# TODO: should add a render_mode optional kwarg
	def __init__(
			self,
			state: Environment_State,
			properties: Environment_Properties,
			movement_system: Movement_System,
			reward_func: Callable[[list[Action_Selection, Environment]], list[float]],
			step_execution_order: Step_Execution_Order = Step_Execution_Order.Entity_Definition_Order
		) -> None:
		'''
		Assumptions:
			- New Agents will not be added to the Environment after initialization. (new Entities can still be added)
		'''
		self.state = state
		self.properties = properties
		self.movement_system = movement_system
		self.reward_func = reward_func
		self.step_execution_order = step_execution_order
		self.reset()

	@abstractmethod
	def observe(self, agent_id: int) -> Observation:
		pass

	# TODO: clarify the responsability of this function (maybe rename it)
	#	currently, I think this function should handle extra random things that happen in the env outside of action interactions
	@abstractmethod
	def environment_start_of_step(self, action_selections: list[Action_Selection]):
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
	def environment_end_of_step(self, action_selections: list[Action_Selection]):
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
		'''This method is used by the reset() method to reset environment specific state.'''
		pass

	def render(self, **kwargs) -> Optional[str]:
		'''This is for visualizing the environment. It is not required to be implemented.'''
		from word_play.renderer import AsciiRenderer
		if not hasattr(self, '_renderer'):
			self._renderer = AsciiRenderer(self)
		return self._renderer.render(**kwargs)
	
	def get_position_color(self, position: Position) -> Optional[str]:
		'''
		Returns the color string for a specific position in the environment.
		Used by the renderer to colorize the terrain.
		Return None to use default rendering.
		'''
		return None

	def reset(self, seed=None) -> None:
		self._reset(seed=seed)
		self._init_agent_list()
		self._init_agent_idx_dict()
		self._add_movement_options_to_agents()
		self._rearrage_entities_to_match_step_execution_order()
		self.last_rewards = [None] * len(self.agents)
		self.terminations = [False] * len(self.agents)
		self.truncations = [False] * len(self.agents)
		self.infos = [{} for _ in self.agents]


	def _init_agent_list(self):
		self.agents = [entity for entity in self.state.entities if isinstance(entity, Agent)]


	def _init_agent_idx_dict(self):
		self.agent_to_idx = {agent: i for i, agent in enumerate(self.agents)}


	# TODO: we are currently not preventing the addition of duplicate actions
	def _add_movement_options_to_agents(self):
		for agent in self.agents:
			agent.actions_on_self += self.movement_system.movement_options


	def _rearrage_entities_to_match_step_execution_order(self):
		if self.step_execution_order == Step_Execution_Order.Entity_Definition_Order:
			pass
		elif self.step_execution_order == Step_Execution_Order.Agents_First:
			non_agents = [entity for entity in self.state.entities if not isinstance(entity, Agent)]
			self.state.entities = self.agents + non_agents
		elif self.step_execution_order == Step_Execution_Order.Agents_Last:
			non_agents = [entity for entity in self.state.entities if not isinstance(entity, Agent)]
			self.state.entities = non_agents + self.agents
		else:
			raise ValueError(f'Invalid step_execution_order: {self.step_execution_order}')


	# TODO: this is a temp implementation which says all actions are valid
	# TODO: we can likely implement this using abstract methods, we don't need to require the env creator to create it
	#	(will likely be done by giving each action a list of validity requirements)
	# TODO: I think a proper implementation of this function would also use Movement_System.movement_is_valid
	def action_selection_is_valid(self, actor, action_selection) -> bool:
		return True


	def _perform_action(self, agent, action_selection: Action_Selection):
		assert self.action_selection_is_valid(agent, action_selection)
		if isinstance(action_selection.action, Action_On_Self):
			action_selection.action(agent, self)
		elif isinstance(action_selection.action, Action_On_Other_Entity):
			action_selection.action(action_selection.target_entity, agent, self)
		else:
			raise ValueError(f'Invalid Action class received: {action_selection.action}')


	def step(self, action_selections: list[Action_Selection]) -> None:
		self.environment_start_of_step(action_selections)
		
		action_selection_iter = iter(action_selections)
		for entity in self.state.entities:
			if isinstance(entity, Agent):
				self._perform_action(entity, next(action_selection_iter))
				# To prevent cheating Agents do not have access to the environment in their step function
				entity.step()
			else:
				entity.step(env=self)

		self.environment_end_of_step(action_selections)
		self.last_rewards = self.reward_func(action_selections, self)
	
	
	def last(self, agent_id: int) -> tuple[Observation, float, bool, bool, dict]:
		'''
		Returns:
		- observation
		- instantaneous reward
		- terminatation status
			has the agent reached a terminal state in the MDP?
		- truncatation status
			has the episode ended due to a reason outside of the scope of the MDP (ex., time limit)?
		- info
		
		for the current agent.
		'''
		return self.observe(agent_id), self.last_rewards[agent_id], self.terminations[agent_id], self.truncations[agent_id], self.infos[agent_id]


	def get_entities_near_position(self, position: Position) -> list[Entity]:
		return [entity for entity in self.state.entities if self.movement_system.positions_are_close(position, entity.state.position)]


	def get_possible_actions(self, agent_id: int) -> list[Action_Selection]:
		agent = self.agents[agent_id]
		nearby_entities = [entity for entity in self.get_entities_near_position(agent.state.position) if entity is not agent]
		possible_actions = [Action_Selection(action=action, target_entity=agent) for action in agent.actions_on_self]
		for entity in nearby_entities:
			possible_actions += [Action_Selection(action=action, target_entity=entity) for action in entity.exposed_actions]
		return possible_actions