from dataclasses import dataclass
from word_play.environment import (
    Action,
    Action_Validation,
    Target_Is_Self,
    Component,
    Entity,
    Position,
    Movement_System,
    Environment,
)
from copy import deepcopy


@dataclass(slots=True)
class Single_Point_Position(Position):
    CONSTANT_POSITION = 0

    def __str__(self):
        return f"{self.CONSTANT_POSITION}"


@dataclass(slots=True)
class Position_1D(Position):
    x: int

    def __str__(self):
        return f"{self.x}"


@dataclass(slots=True)
class Position_2D(Position):
    x: int
    y: int

    def __str__(self):
        return f"({self.x}, {self.y})"


# TODO: ANDREI: THIS CURRENTLY DOES NOT WORK CORRECTLY SINCE IT DEPENDS ON WHO IS MOVING. IT SHOULD WORK NO MATTER WHAT.
#       Perhaps a good approach is to check both target and actor collision comps when moving <-- I think this is good ******
# TODO: ANDREI: need a (tag?) system so you can define what you collide and dont collide with. E.g., agents collide with
#       walls but not each other. Then maybe just update the movement actions to have a validation rule which checks for
#       the collidable component and the correct tags
class Collidable(Component):
    def __init__(
        self,
        collidable_tags: list[str] | None = None,
    ):
        """
        Only entities with the Collidable component interact with the collision system. Each entity has the right to
        specify which entity tags it will to collide with. Note, that collision permission is bi-directional, i.e.,
        entity A can specify it wants to collide with entity B, then regardless of entity B's collision specification
        entity A and B will collide.

        collidable_tags represents the tags that the associated entity can collide with.
        """
        super().__init__()
        self.collidable_tags = collidable_tags or []


def check_for_collision_at_position(target_position: Position, actor: Entity, env: Environment) -> bool:
    collidable_entities_at_position = [
        entity
        for entity in env.state.entities
        if entity.position == target_position and entity.has_component(Collidable) and entity is not actor
    ]

    collidable_tags = {tag for entity in collidable_entities_at_position for tag in entity.tags}
    actor_collision_tags = set(actor.get_component(Collidable).collidable_tags)

    if not actor_collision_tags.isdisjoint(collidable_tags):
        return False

    other_entity_collision_tags = {
        tag for entity in collidable_entities_at_position for tag in entity.get_component(Collidable).collidable_tags
    }

    if not set(actor.tags).isdisjoint(other_entity_collision_tags):
        return False

    return True


# TODO: might be nice to make a nice general version of this class
class No_Collision_Will_Occur(Action_Validation):
    """
    IMPORTANT: this class assumes that movement_action.__call__() causes no mutation of the environment (other than the
    mutation to the actor) or target_entity (in the case that target_entity is not actor). If the movement_action applies
    mutation to the environment, one very simple fix is to create a hypothetical env which is a deepcopy of env.

    IMPORTANT: this class create a deepcopy of the actor. If your actor stores large amounts of data (e.g., an LLM) this
    will be very inefficient and may cause out-of-memory errors.

    IMPORTANT: this class assumes the action has no kwargs.
    """

    def __init__(self, movement_action: Action):
        self.movement_action = movement_action

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not actor.has_component(Collidable):
            return True
        hypothetical_actor = deepcopy(actor)
        self.movement_action(hypothetical_actor, target_entity, env, None)
        return check_for_collision_at_position(hypothetical_actor.position, actor, env)


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


def positions_are_close_if_equal(position_A: Position, position_B: Position) -> bool:
    return position_A == position_B


# TODO: create movement validations for a bounded 1D region and 2D boxes
# 	These might require the addition of a "properties" attribute to the Movement_System class
# 	This would contain things like: max_x, min_x, max_y, min_y, etc.
# 	Idk if this should be a dict or if it should be typeless (it may be conceivable that you might want a custom class)
# 		- i.e., maybe the Movement_System can store the entity positions for fast look-up??? Idk if this is the right place to do that


INFINITE_1D_MOVEMENT_SYSTEM = Movement_System(
    position_type=Position_1D,
    movement_options=(Move_Left(), Move_Right()),
    positions_are_close=positions_are_close_if_equal,
)

INFINITE_2D_MOVEMENT_SYSTEM = Movement_System(
    position_type=Position_2D,
    movement_options=(Move_Left(), Move_Right(), Move_Up(), Move_Down()),
    positions_are_close=positions_are_close_if_equal,
)

SINGLE_POINT_MOVEMENT_SYSTEM = Movement_System(
    position_type=Single_Point_Position,
    movement_options=(),
    positions_are_close=positions_are_close_if_equal,
)
