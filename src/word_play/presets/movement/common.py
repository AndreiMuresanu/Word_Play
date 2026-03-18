from __future__ import annotations

from copy import deepcopy

from word_play.core import (
    Action,
    Action_Validation,
    Component,
    Entity,
    Environment,
    Position,
)


# TODO: ANDREI: THIS CURRENTLY DOES NOT WORK CORRECTLY SINCE IT DEPENDS ON WHO IS MOVING. IT SHOULD WORK NO MATTER WHAT.
#       Perhaps a good approach is to check both target and actor collision comps when moving <-- I think this is good ******
# TODO: ANDREI: need a (tag?) system so you can define what you collide and dont collide with. E.g., agents collide with
#       walls but not each other. Then maybe just update the movement actions to have a validation rule which checks for
#       the collidable component and the correct tags
class Collidable(Component):
    def __init__(self, collidable_tags: list[str] | None = None):
        """
        Only entities with the Collidable component interact with the collision system.

        collidable_tags represents the tags that the associated entity can collide with.

        Collision permission is bi-directional: if either entity opts into colliding with
        the other's tags, the move is blocked.
        """
        super().__init__()
        self.collidable_tags = collidable_tags or []


def positions_are_close_if_equal(position_a: Position, position_b: Position) -> bool:
    return position_a == position_b


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


class No_Collision_Will_Occur(Action_Validation):
    """
    Generic collision validator for movement actions that only mutate the actor's position.

    This validator deep-copies the actor, executes the movement action on the copy, then
    checks whether that destination would collide with the live environment.

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
