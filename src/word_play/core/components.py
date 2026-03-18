from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .actions import Action, Action_Selection
from .observation import Observation

if TYPE_CHECKING:
    from .entity import Entity
    from .environment import Environment


class Component:
    """All Components will inherit from this class."""

    def __init__(self, tags: list[str] | None = None, actions: list[Action] | None = None):
        self.tags: list[str] = tags or []
        self.actions: list[Action] = actions or []
        # NOTE: This is a reference to the entity which owns this component. It is populated when the Entity is initialized
        self.entity: Entity | None = None

    def post_initialization(self) -> None:
        """
        This method is called at the end of the parent entity's __init__ method. This is after all components have been
        initialized (e.g., had their self.entity attribute populated with the parent entity)
        """
        pass

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        """
        This method is called when the entity is instantiated. E.g., when the environment is first created, before any
        steps or actions are executed. Or the moment when a different entity instantiates (creates) this entity while
        the env is running.
        """
        pass

    def pre_actions_step(self, env: Environment) -> None:
        """
        This method is called before all entities execute their actions. It can be overriden to add additional logic to
        the Entity's step function.
        """
        pass

    def post_actions_step(self, env: Environment) -> None:
        # TODO: components which do implement a step function still have the empty step function which still gets run each
        #       step. The compute burden of this is negligible, however, it would still be nice to avoid this
        """
        This method is called after all entities execute their actions. It can be overriden to add additional logic to
        the Entity's step function.
        """
        pass

    def on_destroy(self, env: Environment) -> None:
        """This method is called when the entity is destory. E.g., when an entity dies."""
        pass


class Agent_Policy(Component, ABC):
    """All agents must contain a component inheriting from this class."""

    @abstractmethod
    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        """
        Outputs a tuple containing an Action_Selection and a dict containing information about the selection process.
        E.g., the info dict contain the chain-of-thought trace of an LLM-based agent.
        """
        pass


class Non_Agent_Policy(Component, ABC):
    """
    This component allows non-agent entities to take actions. E.g., an NPC or a cow taking movement actions to wander a
    field.
    """

    @abstractmethod
    def select_action(self, possible_actions: list[Action_Selection], env: Environment) -> Action_Selection:
        pass
