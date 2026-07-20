from __future__ import annotations

from copy import deepcopy
from typing import Callable

from word_play.core import Action, Component, Entity, Environment, Action_Validation, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Doesnt_Have_Tag, Target_Has_Tag


class Room_In_Inventory(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory_comp = actor.get_component(Inventory)
        if inventory_comp.inventory_size < 0:
            return True
        return len(inventory_comp.inventory) < inventory_comp.inventory_size


class Pick_Up_Item(Action):
    def __init__(
        self, collectable_tags: list[str], item_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None
    ):
        super().__init__(
            validation_rules=[
                Target_Has_Tag(collectable_tags),
                Target_Doesnt_Have_Tag(["in_inventory"]),
                Room_In_Inventory(),
                Target_Not_Self(),
                Target_Is_Nearby(item_is_nearby),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.tags.append("in_inventory")
        actor.get_component(Inventory).inventory.append(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Pick up {target_entity.name}."


class In_Actor_Inventory(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return target_entity in actor.get_component(Inventory).inventory


class Drop_Item(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                In_Actor_Inventory(),
                Target_Not_Self(),
                Target_Is_Nearby(),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.tags.remove("in_inventory")
        actor.get_component(Inventory).inventory.remove(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Drop {target_entity.name}."


# TODO: would be nice to add the functionality to have agents start with things in their inventory
# TODO: perhaps there is a nicer solution than the in_inventory tag I'm not sure what issues the tag approach can cause
#       when it interacts with different components. A diff approach is creating entity heirarchies, but this might be
#       overkill.
class Inventory(Component):

    def __init__(
        self, collectable_tags: list[str], inventory_size: int = -1, starting_inventory: list[Entity] | None = None
    ):
        """inventory_size < 0 represents an infinite inventory size."""

        super().__init__(
            actions=[Pick_Up_Item(collectable_tags), Drop_Item()],
        )
        self.inventory_size: int = inventory_size
        self.inventory: list[Entity] = []
        self.starting_inventory = starting_inventory or []

    def add(self, item: Entity, env: Environment | None = None) -> bool:
        """Add an item to the inventory. Returns True if stored, False if no room.

        Sets the ``in_inventory`` tag and, if ``env`` is given and the item
        isn't yet registered, instantiates it in the environment.
        """
        if not (self.inventory_size < 0 or len(self.inventory) < self.inventory_size):
            return False
        self.inventory.append(item)
        if "in_inventory" not in item.tags:
            item.tags.append("in_inventory")
        if env is not None and item not in env.state.entities:
            env.instantiate_entity(item)
        return True

    def remove(self, item: Entity) -> Entity | None:
        """Remove an item from the inventory. Returns the item, or ``None`` if it wasn't present."""
        if item not in self.inventory:
            return None
        self.inventory.remove(item)
        return item

    def on_instantiation(self, env: Environment, seed: int | None) -> None:
        for entity in self.starting_inventory:
            entity.position = deepcopy(self.entity.position)
            env.instantiate_entity(entity)
            self.inventory.append(entity)
            entity.tags.append("in_inventory")

    def post_actions_step(self, env: Environment) -> None:
        for obj_entity in self.inventory:
            # TODO: we can likely do something nicer than a deepcopy (e.g., by adding some kinda of functionality to the
            #       Position class)
            obj_entity.position = deepcopy(self.entity.position)

    def on_destroy(self, env):
        # Drop items on death
        for item in self.inventory:
            item.tags.remove("in_inventory")

        self.inventory = []


def inventory_items(entity: Entity) -> list[Entity]:
    """Items held by an entity, or [] if it has no Inventory component."""
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return []
    return list(inventory.inventory)


def inventory_has_room(entity: Entity, count: int = 1) -> bool:
    """Whether an entity's inventory can hold ``count`` more items. False if it has no Inventory."""
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return False
    return inventory.inventory_size < 0 or len(inventory.inventory) + count <= inventory.inventory_size
