from __future__ import annotations

from typing import TYPE_CHECKING

from .actions import Action
from .components import Agent_Policy, Component, Non_Agent_Policy
from .movement import Position

if TYPE_CHECKING:
    from .environment import Environment


class Entity:
    def __init__(
        self,
        name: str,
        position: Position,
        tags: list[str] | None = None,
        actions: list[Action] | None = None,
        components: list[Component] | None = None,
    ):
        # Additional information is added to the state using components. The component state can be accessed
        # using self.get_component(ComponentType)
        self.name: str = name
        self.position: Position = position

        self._init_components(components)
        self._init_actions(actions)
        self._init_tags(tags)
        self.is_agent: bool = self.has_component(Agent_Policy)

        assert not (self.has_component(Agent_Policy) and self.has_component(Non_Agent_Policy))

        self.post_initialization()

    def _init_components(self, components: list[Component] | None) -> None:
        components = components or []
        # We require that each component be of a unique type
        assert len({type(comp) for comp in components}) == len(components)
        self.components: dict[type[Component], Component] = {type(comp): comp for comp in components}

        for comp in self.components.values():
            comp.entity = self

    def _init_actions(self, actions: list[Action] | None) -> None:
        self.actions: list[Action] = actions or []
        for component in self.components.values():
            self.actions += component.actions

    def _init_tags(self, tags: list[str] | None) -> None:
        self.tags: list[str] = tags or []
        for component in self.components.values():
            self.tags += component.tags

    def get_component[T: Component](self, component_type: type[T]) -> T | None:
        """
        If multiple components match the specified component type (e.g., in the case where you have two components
        inheriting from component_type), this method simply returns the first component. Use get_all_components if you
        want all of the matching components.
        """
        valid_components = [comp for comp in self.components.values() if isinstance(comp, component_type)]
        if len(valid_components) == 0:
            return None
        return valid_components[0]

    def get_component_exact(self, component_type: type[Component]) -> Component | None:
        if component_type in self.components:
            return self.components[component_type]
        return None

    def get_all_components(self, component_type: type[Component]) -> list[Component]:
        return [comp for comp in self.components.values() if isinstance(comp, component_type)]

    def has_component(self, component_type: type[Component]) -> bool:
        return any(isinstance(comp, component_type) for comp in self.components.values())

    def has_component_exact(self, component_type: type[Component]) -> bool:
        return any(ctype == component_type for ctype in self.components.keys())

    def has_action_type(self, action_type: type[Action]) -> bool:
        return any(isinstance(action, action_type) for action in self.actions)

    def post_initialization(self) -> None:
        # NOTE: for Python 3.7+ key insertion ordering is perserved. Hence, components will execute in definition order
        for component in self.components.values():
            component.post_initialization()

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        # NOTE: for Python 3.7+ key insertion ordering is perserved. Hence, components will execute in definition order
        for component in self.components.values():
            component.on_instantiation(env, seed)

    def pre_actions_step(self, env: Environment) -> None:
        # NOTE: for Python 3.7+ key insertion ordering is perserved. Hence, components will execute in definition order
        for component in self.components.values():
            component.pre_actions_step(env)

    def post_actions_step(self, env: Environment) -> None:
        # NOTE: for Python 3.7+ key insertion ordering is perserved. Hence, components will execute in definition order
        for component in self.components.values():
            component.post_actions_step(env)

    def on_destroy(self, env: Environment) -> None:
        # NOTE: for Python 3.7+ key insertion ordering is perserved. Hence, components will execute in definition order
        for component in self.components.values():
            component.on_destroy(env)
