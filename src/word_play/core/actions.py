from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .entity import Entity
    from .environment import Environment


class Action_Validation(ABC):
    @abstractmethod
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        pass


class Target_Is_Self(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return actor is target_entity


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
        return env.movement_system.positions_are_close(actor.position, target_entity.position)


# TODO: this system is a bit messy. It could integrate better with env.possible_actions and Action_Validation. Right now
#       there are two types of is_valid checks. One performed by the env to identify possible actions and one performed
#       by the Action_Arg when the user selects their action's args to make sure the arg selection is valid. Ideally
#       only a single system would exist. But this would very likely require a substantial refactor.
class Action_Arg(ABC):
    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
        """validators are functions which take as input (arg, actor, target_entity, env) and return a bool."""
        self.validators = validators or []

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

    def parse_and_validate_kwarg_list(self, input_str: str, value_sep: str = ";") -> dict:
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

    def parse_and_validate_kwarg_dict(self, input_str: str, pair_sep: str = ",", kv_sep: str = ":") -> dict:
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
