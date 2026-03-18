from __future__ import annotations

import re
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from word_play.core import Entity, Environment

from word_play.core import Action_Arg


class Int_Arg(Action_Arg):
    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
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
        self.min = min
        self.max = max
        super().__init__(validators=[arg_in_range(min, max)])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"int in [{self.min}, {self.max})"


class Float_Arg(Action_Arg):
    def __init__(self, validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None):
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
        return (
            f"list, e.g., 'item1{self.item_sep} item2{self.item_sep} ...'. "
            f"Each item is of type: {self.item_arg.arg_description(actor, target_entity, env)}"
        )


class Dict_Arg(Action_Arg):
    def __init__(
        self,
        key_arg: Action_Arg,
        value_arg: Action_Arg,
        pair_sep: str = ",",
        kv_sep: str = ":",
        validators: list[Callable[[Any, Entity, Entity, Environment], bool]] | None = None,
    ):
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
        return (
            f"dict, e.g., 'key1{self.kv_sep} item1{self.pair_sep} ...'. Each key is of type: "
            f"{self.key_arg.arg_description(actor, target_entity, env)}. Each value of type: "
            f"{self.value_arg.arg_description(actor, target_entity, env)}"
        )
