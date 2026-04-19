from __future__ import annotations

from copy import deepcopy
from typing import Callable

from word_play.core import (
    Action,
    Action_Arg,
    Action_Validation,
    Component,
    Entity,
    Environment,
    Target_Is_Nearby,
    Target_Is_Self,
    Target_Not_Self,
)
from word_play.presets.action_validations import Target_Doesnt_Have_Tag, Target_Has_Component, Target_Has_Tag


class Room_In_Inventory(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory_comp = actor.get_component(Inventory)
        if inventory_comp.inventory_size < 0:
            return True
        return len(inventory_comp.inventory) < inventory_comp.inventory_size


class Inventory_Item_Index_Arg(Action_Arg):
    def parse(self, input: str) -> int:
        return int(input)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        inventory = actor.get_component(Inventory)
        if inventory is None or not inventory.inventory:
            return "inventory index (currently no items)"
        options = ", ".join(f"{idx}:{item.name}" for idx, item in enumerate(inventory.inventory))
        return f"inventory index ({options})"

    def is_valid(self, arg, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        inventory = actor.get_component(Inventory)
        return (
            inventory is not None
            and isinstance(arg, int)
            and 0 <= arg < len(inventory.inventory)
        )


def container_holding(entity: Entity) -> "Single_Item_Holder | None":
    return entity.get_component(Single_Item_Holder)


def container_holding_item(env: Environment, item: Entity) -> "Single_Item_Holder | None":
    for entity in env.state.entities:
        holder = container_holding(entity)
        if holder is not None and holder.stored_item is item:
            return holder
    return None


class Pick_Up_Item(Action):
    def __init__(
        self, collectable_tags: list[str], item_is_nearby: Callable[[Entity, Entity, Environment], bool] | None = None
    ):
        super().__init__(
            validation_rules=[
                Target_Has_Tag(collectable_tags),
                Target_Doesnt_Have_Tag(["in_inventory"]),
                Target_Doesnt_Have_Tag(["hidden_in_container"]),
                Room_In_Inventory(),
                Target_Not_Self(),
                Target_Is_Nearby(item_is_nearby),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        holder = container_holding_item(env, target_entity)
        if holder is not None:
            holder.stored_item = None
        if "in_container" in target_entity.tags:
            target_entity.tags.remove("in_container")
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


class Single_Item_Holder(Component):
    def __init__(self, accepted_item_tags: list[str] | None = None):
        super().__init__(actions=[Put_In_Container()])
        self.accepted_item_tags = accepted_item_tags or []
        self.stored_item: Entity | None = None

    def accepts(self, item: Entity) -> bool:
        if self.stored_item is not None:
            return False
        if not self.accepted_item_tags:
            return True
        return any(tag in item.tags for tag in self.accepted_item_tags)

    def post_actions_step(self, env: Environment) -> None:
        if self.stored_item is not None:
            self.stored_item.position = deepcopy(self.entity.position)

    def on_destroy(self, env: Environment) -> None:
        if self.stored_item is not None and "in_container" in self.stored_item.tags:
            self.stored_item.tags.remove("in_container")
        self.stored_item = None


class Put_In_Container(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Single_Item_Holder),
            ],
            required_kwargs={"inventory index": Inventory_Item_Index_Arg()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None
        inventory = actor.get_component(Inventory)
        holder = target_entity.get_component(Single_Item_Holder)
        assert inventory is not None
        assert holder is not None

        item = inventory.inventory[int(kwargs["inventory index"])]
        if not holder.accepts(item):
            raise ValueError(f"{target_entity.name} cannot accept {item.name}.")

        inventory.inventory.remove(item)
        if "in_inventory" in item.tags:
            item.tags.remove("in_inventory")
        if "in_container" not in item.tags:
            item.tags.append("in_container")
        item.position = deepcopy(target_entity.position)

        # Ensure the item is in the environment so it can be interacted with
        if item not in env.state.entities:
            env.instantiate_entity(item)
        holder.stored_item = item
        return {"stored_item": item.name}

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        if not super().is_valid(actor, target_entity, env, kwargs=kwargs):
            return False
        if kwargs == "unconsidered" or kwargs is None:
            return True
        holder = target_entity.get_component(Single_Item_Holder)
        inventory = actor.get_component(Inventory)
        if holder is None or inventory is None:
            return False
        item = inventory.inventory[int(kwargs["inventory index"])]
        return holder.accepts(item)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Put an inventory item into {target_entity.name}."


class Discard_Item(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self()],
            required_kwargs={"inventory index": Inventory_Item_Index_Arg()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None
        inventory = actor.get_component(Inventory)
        assert inventory is not None
        item = inventory.inventory.pop(int(kwargs["inventory index"]))
        if "in_inventory" in item.tags:
            item.tags.remove("in_inventory")
        if item in env.state.entities:
            env.destroy_entity(item)
        return {"discarded_item": item.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Discard an inventory item."


def materialize_item(spec: Entity | Callable[[], Entity]) -> Entity:
    entity = spec() if callable(spec) else deepcopy(spec)
    if not isinstance(entity, Entity):
        raise TypeError("Expected an Entity or a factory that returns an Entity.")
    return entity


class Infinite_Item_Source(Component):
    def __init__(self, item_factory: Entity | Callable[[], Entity]):
        super().__init__(actions=[Dispense_From_Infinite_Source()])
        self.item_factory = item_factory

    def create_item(self) -> Entity:
        return materialize_item(self.item_factory)


class Dispense_From_Infinite_Source(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Infinite_Item_Source),
            ]
        )

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        return super().is_valid(actor, target_entity, env, kwargs=kwargs)

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        source = target_entity.get_component(Infinite_Item_Source)
        assert source is not None

        item = source.create_item()
        item.position = deepcopy(target_entity.position)
        env.instantiate_entity(item)
        return {"spawned_item": item.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Dispense an item from {target_entity.name}."


Take_From_Infinite_Source = Dispense_From_Infinite_Source


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
            actions=[Pick_Up_Item(collectable_tags), Drop_Item(), Discard_Item()],
        )
        self.inventory_size: int = inventory_size
        self.inventory: list[Entity] = []
        self.starting_inventory = starting_inventory or []

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
