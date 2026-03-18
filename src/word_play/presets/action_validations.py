from __future__ import annotations

from typing import TYPE_CHECKING

from word_play.core import (
    Action_Validation,
    Target_Is_Nearby,
    Target_Is_Self,
    Target_Not_Self,
)

"""
Built-in Action_Validation classes.

`Target_Is_Self`, `Target_Not_Self`, and `Target_Is_Nearby` remain implemented in
core because `Environment.possible_actions()` relies on their concrete classes for
search optimizations. They are re-exported here so users can discover and import
all built-in validators from one place.

Those three validators have special meaning to the engine:

- `Target_Is_Self` restricts the action's target to the acting entity itself. This
  is the right validator for actions like waiting, moving, healing yourself, or
  any other action that conceptually targets "me".
- `Target_Not_Self` excludes the acting entity from the candidate targets. This is
  useful for actions that may target many entities but should never target the
  actor.
- `Target_Is_Nearby` restricts candidate targets to entities considered nearby by
  the environment's movement system. This is useful for local interactions like
  melee attacks, pickup actions, and trading with adjacent entities.

Because `Environment.possible_actions()` recognizes these concrete classes, using
them can substantially reduce the number of target entities the engine needs to
check when enumerating actions.
"""

if TYPE_CHECKING:
    from word_play.core import Component, Entity, Environment


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
