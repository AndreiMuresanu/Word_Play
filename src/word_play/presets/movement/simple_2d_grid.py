from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from word_play.core import (
    Action,
    Action_Validation,
    Entity,
    Environment,
    Movement_System,
    Position,
    Target_Is_Self,
)
from word_play.presets.movement.common import (
    Collidable,
    check_for_collision_at_position,
)


@dataclass(slots=True)
class Position_2D(Position):
    x: int
    y: int

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"


class No_Collision_Will_Occur_Left(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not actor.has_component(Collidable):
            return True

        target_position = deepcopy(actor.position)
        target_position.x -= 1
        return check_for_collision_at_position(target_position, actor, env)


class No_Collision_Will_Occur_Right(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not actor.has_component(Collidable):
            return True

        target_position = deepcopy(actor.position)
        target_position.x += 1
        return check_for_collision_at_position(target_position, actor, env)


class No_Collision_Will_Occur_Up(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not actor.has_component(Collidable):
            return True

        target_position = deepcopy(actor.position)
        target_position.y += 1
        return check_for_collision_at_position(target_position, actor, env)


class No_Collision_Will_Occur_Down(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not actor.has_component(Collidable):
            return True

        target_position = deepcopy(actor.position)
        target_position.y -= 1
        return check_for_collision_at_position(target_position, actor, env)


class Move_Left(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), No_Collision_Will_Occur_Left()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        actor.position.x -= 1

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Move left."


class Move_Right(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), No_Collision_Will_Occur_Right()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        actor.position.x += 1

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Move right."


class Move_Up(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), No_Collision_Will_Occur_Up()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        actor.position.y += 1

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Move up."


class Move_Down(Action):
    def __init__(self):
        super().__init__(validation_rules=[Target_Is_Self(), No_Collision_Will_Occur_Down()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        actor.position.y -= 1

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Move down."


def positions_are_close_if_same_or_adjacent(position_a: Position_2D, position_b: Position_2D) -> bool:
    return abs(position_a.x - position_b.x) + abs(position_a.y - position_b.y) <= 1


INFINITE_2D_MOVEMENT_SYSTEM = Movement_System(
    position_type=Position_2D,
    movement_options=[Move_Left(), Move_Right(), Move_Up(), Move_Down()],
    positions_are_close=positions_are_close_if_same_or_adjacent,
)
