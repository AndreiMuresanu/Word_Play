from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NamedTuple, Callable, Any
import random
import re


# ---------------------------------------- Movement System Definition ----------------------------------------


# TODO: do we need to add an abstract __eq__ method? tbd as needs arise
@dataclass(slots=True)
class Position(ABC):
    # We keep Position as an ABC with no assumption because environments may have non-coordinate based positions.
    # For example, consider the enum based location-wise (ie., graph-based) positions: 'market', 'office', 'home', etc.
    # additionally, position comparison functions (ex., '>') may be useful
    @abstractmethod
    def __str__(self):
        pass


# TODO: need to check that position_type is being validated in a nice way
# TODO: maybe this can be made simpler and more effecient (we can likely sacrifice some generality)
@dataclass(slots=True)
class Movement_System:
    position_type: Position
    # TODO: ANDREI: currently movement_options is unused. I like the idea of clearly defining what the movement actions
    #       are since this can reduce confusion about which movement actions related to which position type. But this is
    #       likely not the best approach
    movement_options: list[Action]
    positions_are_close: Callable[[Position, Position], bool]


# ---------------------------------------- Action Definition ----------------------------------------


# TODO: would be nice to support actions with additional custom input params. For example, Move_To_Location(location) is
# 		otherwise awkward to implement.
# TODO: might be nice if actions return some kinda of value in order to communicate success/failure/info back to env/agent.
# 		For example, if the action is to roll a dice, you need to know what number you rolled.
# TODO: implementing Action using a class might not be the nicest approach. It might be nicer to user a dataclass or namedtuple.
# 		Maybe we can replace the Action ABC with a protocol?
# TODO: maybe action should have a can_perform_action(actor) method? This might make it nice to check for action validity
# class Action(ABC):
#     pass


class Action_Validation(ABC):
    @abstractmethod
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        pass


# TODO: would be nice to move action validations to preset file. But that would cause a circular import...
class Target_Is_Self(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return actor == target_entity


class Target_Not_Self(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return actor is not target_entity


class Target_Is_Nearby(Action_Validation):
    def __init__(self, target_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None):
        """By the defeault function describing nearby entities is the movement system's positions_are_close function."""
        self.target_is_nearby = target_is_nearby

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if self.target_is_nearby:
            return self.target_is_nearby(actor, target_entity, env)
        else:
            return env.movement_system.positions_are_close(actor.position, target_entity.position)


class Target_Has_Tag(Action_Validation):

    def __init__(self, target_tags: list[str]):
        self.target_tags: list[str] = target_tags

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return any(tag in target_entity.tags for tag in self.target_tags)


class Target_Doesnt_Have_Tag(Action_Validation):

    def __init__(self, target_tags: list[str]):
        self.target_tags: list[str] = target_tags

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return all(tag not in target_entity.tags for tag in self.target_tags)


class Target_Has_Component(Action_Validation):

    def __init__(self, target_component: type[Component]):
        self.target_component: type[Component] = target_component

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return target_entity.get_component(self.target_component) is not None


# TODO: this system is a bit messy. It could integrate better with env.possible_actions and Action_Validation. Right now
#       there are two types of is_valid checks. One performed by the env to identify possible actions and one performed
#       by the Action_Arg when the user selects their action's args to make sure the arg selection is valid. Ideally
#       only a single system would exist. But this would very likely require a substantial refactor.
class Action_Arg(ABC):

    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.validators = validators

    @abstractmethod
    def parse(self, input: str):
        pass

    @abstractmethod
    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        pass

    def is_valid(self, arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return all(validator(arg, actor, target_entity, env) for validator in self.validators)

    def parse_and_validate(self, input: str, actor: Entity, target_entitiy: Entity, env: Environment):
        arg = self.parse(input)

        if not self.is_valid(arg, actor, target_entitiy, env):
            raise ValueError(f"Invalid input: '{input}'")

        return arg


class Int_Arg(Action_Arg):

    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        validators = validators or []
        validators.append(lambda arg, actor, target_entity, env: isinstance(arg, int))
        super().__init__(validators)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "int"

    def parse(self, input: str) -> int:
        return int(input)


def arg_in_range(min=None, max=None) -> Callable:
    def validator(arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if min is not None and arg < min:
            return False

        if max is not None and arg >= max:
            return False

        return True

    return validator


class Int_Range_Arg(Int_Arg):

    def __init__(self, min: int | None = None, max: int | None = None):
        """
        min is inclusive. max is exclusive.
        validators are functions which take as input (arg, actor, target_entity, env) and return a bool.
        """
        self.min = min
        self.max = max
        super().__init__(validators=[arg_in_range(min, max)])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"int in [{self.min}, {self.max})"


class Float_Arg(Action_Arg):

    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        validators = validators or []
        validators.append(lambda arg, actor, target_entity, env: isinstance(arg, float))
        super().__init__(validators)

    def parse(self, input: str) -> float:
        return float(input)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "float"


class Bool_Arg(Action_Arg):

    TRUE_VALUES = {"true", "1", "yes", "y", "on"}
    FALSE_VALUES = {"false", "0", "no", "n", "off"}

    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        validators = validators or []
        validators.append(lambda arg, actor, target_entity, env: isinstance(arg, bool))
        super().__init__(validators)

    def parse(self, input: str) -> bool:
        val = input.lower()

        if val in self.TRUE_VALUES:
            return True

        if val in self.FALSE_VALUES:
            return False

        raise ValueError("Invalid boolean")

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "bool"


class String_Arg(Action_Arg):

    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        validators = validators or []
        validators.append(lambda arg, actor, target_entity, env: isinstance(arg, str))
        super().__init__(validators)

    def parse(self, input: str) -> str:
        return input

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "str"


def arg_matches_regex(pattern: str):
    def validator(arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return bool(re.compile(pattern).fullmatch(arg))

    return validator


class Regex_String_Arg(String_Arg):

    def __init__(
        self, pattern: str, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None
    ):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        validators = validators or []
        validators.append(arg_matches_regex(pattern))
        super().__init__(validators)


def arg_in_set(choice_set: set) -> Callable:
    def validator(arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return arg in choice_set

    return validator


class Choice_Arg(Action_Arg):

    def __init__(
        self,
        choices: set,
        parser: Callable[[str], Any],
        validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None,
    ):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.parser = parser
        self.choices = choices

        validators = validators or []
        validators.append(arg_in_set(choices))
        super().__init__(validators=validators)

    def parse(self, input: str):
        return self.parser(input)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"elment in {self.choices}"


class String_Choice_Arg(Choice_Arg):
    def __init__(self, choices: set[str]):
        super().__init__(choices=choices, parser=str)


class Int_Choice_Arg(Choice_Arg):
    def __init__(self, choices: set[int]):
        super().__init__(choices=choices, parser=int)


def arg_in_choice_fn_result(choice_fn: Callable[[Entity, Entity, Environment], set]) -> Callable:
    def validator(arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return arg in choice_fn(actor, target_entity, env)

    return validator


class Dynamic_Choice_Arg(Action_Arg):

    def __init__(
        self,
        choice_fn: Callable[[Entity, Entity, Environment], set],
        parser: Callable[[str], Any],
        validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None,
    ):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.parser = parser
        self.choice_fn = choice_fn

        validators = validators or []
        validators.append(arg_in_choice_fn_result(choice_fn))
        super().__init__(validators=validators)

    def parse(self, input: str):
        return self.parser(input)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"elment in {self.choice_fn(actor, target_entity, env)}"


class List_Arg(Action_Arg):

    def __init__(
        self,
        item_arg: Action_Arg,
        item_sep=",",
        validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None,
    ):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.item_sep = item_sep
        self.item_arg = item_arg

        validators = validators or []
        validators.append(
            lambda arg, actor, target_entity, env: all(
                item_arg.is_valid(item, actor, target_entity, env) for item in arg
            )
        )
        super().__init__(validators)

    def parse(self, input: str) -> list:
        if not input.strip():
            return []

        items = input.split(self.item_sep)
        return [self.item_arg.parse(i.strip()) for i in items]

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"list, e.g., 'item1{self.item_sep} item2{self.item_sep} ...'. Each item is of type: {self.item_arg.arg_description(actor, target_entity, env)}"


class Dict_Arg(Action_Arg):

    def __init__(
        self,
        key_arg: Action_Arg,
        value_arg: Action_Arg,
        pair_sep: str = ",",
        kv_sep: str = ":",
        validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None,
    ):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.key_arg = key_arg
        self.value_arg = value_arg
        self.pair_sep = pair_sep
        self.kv_sep = kv_sep

        validators = validators or []
        validators.append(self.dict_validator)
        super().__init__(validators)

    def parse(self, input: str) -> dict:
        if not input.strip():
            return {}

        result = {}

        if input == "":
            return result

        pairs = input.split(self.pair_sep)

        for pair in pairs:

            if self.kv_sep not in pair:
                raise ValueError(f"Invalid key/value pair: '{pair}'")

            key_str, value_str = pair.split(self.kv_sep, 1)

            try:
                key = self.key_arg.parse(key_str.strip())
            except Exception as e:
                raise ValueError(f"Invalid key '{key_str}'") from e

            try:
                value = self.value_arg.parse(value_str.strip())
            except Exception as e:
                raise ValueError(f"Invalid value '{value_str}'") from e

            if key in result:
                raise ValueError(f"Duplicate key '{key}'")

            result[key] = value

        return result

    def dict_validator(self, arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        for k, v in arg.items():
            if not self.key_arg.is_valid(k, actor, target_entity, env):
                return False
            if not self.value_arg.is_valid(v, actor, target_entity, env):
                return False

        return True

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"dict, e.g., 'key1{self.kv_sep} item1{self.pair_sep} ...'. Each key is of type: {self.key_arg.arg_description(actor, target_entity, env)}. Each value of type: {self.value_arg.arg_description(actor, target_entity, env)}"


class Action(ABC):

    def __init__(
        self,
        validation_rules: list[Action_Validation] | None = None,
        required_kwargs: dict[str, Action_Arg] | None = None,
    ):
        """required_kwargs is a dictionary with the following format: {"arg_name": Action_Arg, ...}"""
        self.validation_rules = validation_rules or []
        self.required_kwargs = required_kwargs

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert self.is_valid(actor, target_entity, env, kwargs=kwargs)
        return self.exec_action(actor, target_entity, env, kwargs)

    @abstractmethod
    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        """
        This method optionally returns a dict containing information about its execution. E.g., if you roll a dice, the
        result of the roll.
        """
        pass

    @abstractmethod
    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        pass

    # TODO: the "unconsidered" logic is messy. Some of this is unavoidable without a large refactor. Perhaps a small
    #       change to slightly improve things would be to make kwargs: dict | None and nothing else. I.e., None will
    #       replace "unconsidered" and actions with no required_kwargs will have required_kwargs = {} instead of None
    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        validation_rules_pass = all(rule.is_valid(actor, target_entity, env) for rule in self.validation_rules)

        if kwargs == "unconsidered":
            return validation_rules_pass

        args_are_valid = True
        if self.required_kwargs:
            if kwargs is None:
                args_are_valid = False
            else:
                for arg, arg_type in zip(kwargs.values(), self.required_kwargs.values()):
                    if not arg_type.is_valid(arg, actor, target_entity, env):
                        args_are_valid = False
                        break

        return args_are_valid and validation_rules_pass


# TODO: ANDREI: this class is not general enough to support full action flexability, since all actions will have the
#       same targets. E.g., you won't be able to move and attack or heal yourself and attack.
#       NOTE: actually, I think are also two types of action composition: parallel actions and sequential actions. And
#       you can, for example, have a sequence of parallel actions or a parallelization of sequential actions. Parallel
#       actions execute at the same time and sequential actions execute in sequence. However, in our environment we
#       distinctly forbid parallel logic, i.e., only a single action may execute at one time. This means that only
#       sequential actions (action sequences/action chains) exist. For these chains, the question of how to implement
#       their is_valid method arises. E.g., should is_valid. Continuing discussion in notes...
# TODO: ANDREI: we could find all possible targets for each non-first action in the chain, but we would require
#       additional decision steps to choose between them. We could enumerate the full tree of possible action chains to
#       the agent at the start of the step and have each of these be distinct actions, but the chain could be huge...
# TODO: doesn't currently check for kwargs being valid and doesn't take as input a list of kwargs.
class Action_Chain(Action):
    def __init__(self, composed_actions: list[Action]):
        assert len(composed_actions) > 0, "Action_Chain requires at least 1 actions be initialized."
        self.composed_actions = composed_actions

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        for action in self.composed_actions:
            if action.is_valid(actor, target_entity, env):
                action(actor, target_entity, env)

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        return self.composed_actions[0].is_valid(actor, target_entity, env, kwargs=kwargs)


@dataclass(slots=True)
class Action_Selection:
    action: Action
    action_kwargs: dict | None
    actor: Entity
    target_entity: Entity
    env: Environment

    def __str__(self) -> str:
        return self.action.action_description_text(self.actor, self.target_entity, self.env)

    def is_valid(self) -> bool:
        return self.action.is_valid(self.actor, self.target_entity, self.env, kwargs=self.action_kwargs)

    @property
    def required_kwargs(self) -> dict[str, Action_Arg] | None:
        return self.action.required_kwargs

    def parse_and_validate_kwarg_list(
        self,
        input_str: str,
        value_sep: str = ";",
    ) -> dict:
        """
        Parse positional argument input like:
        "val1; val2; val3"
        into:
        {arg1: val1, arg2: val2, arg3: val3}
        """

        if not self.required_kwargs:
            return {}

        arg_names = list(self.required_kwargs.keys())

        parts = [p.strip() for p in input_str.split(value_sep)]

        if len(parts) != len(arg_names):
            raise ValueError(f"Expected {len(arg_names)} arguments but received {len(parts)}")

        parsed = {}

        for name, raw_value in zip(arg_names, parts):
            arg_parser = self.required_kwargs[name]
            parsed[name] = arg_parser.parse_and_validate(raw_value, self.actor, self.target_entity, self.env)

        return parsed

    def parse_and_validate_kwarg_dict(
        self,
        input_str: str,
        pair_sep: str = ",",
        kv_sep: str = ":",
    ) -> dict:
        """
        Parse key/value argument input like:
        "arg1:val1, arg2=:val2"
        into:
        {arg1: val1, arg2: val2}
        """

        if not self.required_kwargs:
            return {}

        parsed = {}

        pairs = [p.strip() for p in input_str.split(pair_sep)]

        for pair in pairs:

            if kv_sep not in pair:
                raise ValueError(f"Invalid argument format: '{pair}'")

            name, raw_value = pair.split(kv_sep, 1)
            name = name.strip()
            raw_value = raw_value.strip()

            if name not in self.required_kwargs:
                raise ValueError(f"Unexpected argument '{name}'")

            arg_parser = self.required_kwargs[name]

            parsed[name] = arg_parser.parse_and_validate(raw_value, self.actor, self.target_entity, self.env)

        missing = set(self.required_kwargs) - set(parsed)

        if missing:
            raise ValueError(f"Missing required arguments: {', '.join(missing)}")

        return parsed


# ---------------------------------------- Observation Definition ----------------------------------------


# TODO: we might want to have this be a subclass of Observation named EntityObservation
# 	in order to perserve the ability for people to create fully customizable and minimal envs
# NOTE: We delibrately exclude a default __str__ method to force env creators to think about it
# 	(We may rethink this decision at some point)
@dataclass(slots=True)
class Observation(ABC):
    possible_actions: list[Action_Selection]

    @abstractmethod
    def __str__(self):
        pass


# ---------------------------------------- Component Definition ----------------------------------------


class Component:
    """All Components will inherit from this class."""

    def __init__(
        self,
        tags: list[str] | None = None,
        actions: list[Action] | None = None,
    ):
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

    # TODO: components which do implement a step function still have the empty step function which still gets run each
    #       step. The compute burden of this is negligible, however, it would still be nice to avoid this
    def post_actions_step(self, env: Environment) -> None:
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


# ---------------------------------------- Entity Definition ----------------------------------------


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
        return any([isinstance(comp, component_type) for comp in self.components.values()])

    def has_component_exact(self, component_type: type[Component]) -> bool:
        return any([ctype == component_type for ctype in self.components.keys()])

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


# ---------------------------------------- Environment Definition ----------------------------------------


# TODO: move to presets
def entity_definition_order(entities: list[Entity], env: Environment) -> list[int]:
    return list(range(len(entities)))


def random_order(entities: list[Entity], env: Environment) -> list[int]:
    new_order = list(range(len(entities)))
    random.shuffle(new_order)
    return new_order


def randomize_agent_order(entities: list[Entity], env: Environment) -> list[int]:
    # This is not the current ordering of agents since the order of the self.agents list does not change. But shuffling
    # self.agents' order or the current agent order are both equivalent.
    new_agent_order = list(range(len(env.agents)))
    random.shuffle(new_agent_order)

    new_agent_order_iter = iter(new_agent_order)
    return [next(new_agent_order_iter) if entity.is_agent else entity_idx for entity_idx, entity in enumerate(entities)]


# TODO: likely delete this and have it be part of the class attrs. Or at least make the env class initializable without
#       this class (i.e., you just pass in the args)
@dataclass(slots=True)
class Environment_State:
    """
    Environments can inherit from the this class to track more complex states.

    The order of the entity list defines the order in which their step functions and actions execute.
    """

    entities: list[Entity]


# TODO: Terminations and truncations are currently unsused.
# TODO: need to make agent_id more general then an int. This way we can make a general last() method which returns
# 	a dict of indexed by agent_id. You can imagine the usage being: a user loads an env and now instantly knows what
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
        state: Environment_State,
        movement_system: Movement_System,
        # TODO: I could default the reward_func to the no_reward func
        reward_func: Callable[[list[Action_Selection, Environment]], list[float]],
        entity_order: Callable[[list[Entity], Environment], list[int]] = entity_definition_order,
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
        self.state = state
        self.movement_system = movement_system
        self.reward_func = reward_func
        self.entity_order = entity_order
        self.reset()

    @abstractmethod
    def observe(self, agent_id: int) -> Observation:
        pass

    # TODO: clarify the responsability of this function (maybe rename it)
    # 	currently, I think this function should handle extra random things that happen in the env outside of action interactions
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

    def render(self) -> None:
        """This is for visualizing the environment. It is not required to be implemented."""
        raise NotImplementedError("This environment does not support rendering.")

    def reset(self, seed=None) -> None:
        self.cur_episode_seed = seed
        self._reset(seed=seed)
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
        nearby_entities = [entity for entity in self.entities_near_position(entity.position)]

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

    # TODO: perhaps I should think about when I want new entities to be initialized. E.g., only at the end of the
    #       current step or only at the start of the next step.
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
