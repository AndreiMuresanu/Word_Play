from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.inventory import Inventory, Inventory_Item_Index_Arg, materialize_item


@dataclass(slots=True)
class Crafter_Recipe:
    input_names: tuple[str, ...]
    output: Entity | Callable[[], Entity]
    duration: int = 0


class Crafter(Component):
    def __init__(self, recipes: list[Crafter_Recipe]):
        super().__init__(actions=[Load_Crafter()])
        self.recipes = recipes
        self.staged_inputs: list[str] = []
        self.active_recipe: Crafter_Recipe | None = None
        self.remaining_steps: int | None = None
        self.ready_recipe: Crafter_Recipe | None = None

    def can_accept(self, item: Entity) -> bool:
        if self.ready_recipe is not None or self.active_recipe is not None:
            return False

        next_inputs = self.staged_inputs + [item.name]
        return any(self._matches_partial(recipe, next_inputs) for recipe in self.recipes)

    def load_item(self, item: Entity) -> None:
        self.staged_inputs.append(item.name)
        for recipe in self.recipes:
            if sorted(self.staged_inputs) == sorted(recipe.input_names):
                self.active_recipe = recipe
                if recipe.duration <= 0:
                    self.ready_recipe = recipe
                    self.active_recipe = None
                    self.remaining_steps = None
                else:
                    self.remaining_steps = recipe.duration
                return

    def advance(self, env: Environment | None = None) -> bool:
        if self.remaining_steps is None or self.active_recipe is None:
            return False

        self.remaining_steps -= 1
        if self.remaining_steps <= 0:
            self.ready_recipe = self.active_recipe
            self.active_recipe = None
            self.remaining_steps = None
            if env is not None:
                self.release_output(env)
            return True
        return False

    def post_actions_step(self, env: Environment) -> None:
        self.advance(env)

    def collect_output(self) -> Entity:
        if self.ready_recipe is None:
            raise ValueError("Crafter has no ready output to collect.")
        recipe = self.ready_recipe
        self.staged_inputs = []
        self.ready_recipe = None
        return materialize_item(recipe.output)

    def release_output(self, env: Environment) -> Entity:
        item = self.collect_output()
        item.position = copy_position(self.entity.position)
        env.instantiate_entity(item)
        return item

    @staticmethod
    def _matches_partial(recipe: Crafter_Recipe, candidate_inputs: list[str]) -> bool:
        remaining = list(recipe.input_names)
        for item_name in candidate_inputs:
            if item_name not in remaining:
                return False
            remaining.remove(item_name)
        return True


class Load_Crafter(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Crafter),
            ],
            required_kwargs={"inventory index": Inventory_Item_Index_Arg()},
        )

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        if not super().is_valid(actor, target_entity, env, kwargs=kwargs):
            return False
        if actor.get_component(Inventory) is None:
            return False
        if kwargs in {"unconsidered", None}:
            return True
        inventory = actor.get_component(Inventory)
        crafter = target_entity.get_component(Crafter)
        item = inventory.inventory[int(kwargs["inventory index"])]
        return crafter.can_accept(item)

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None
        inventory = actor.get_component(Inventory)
        crafter = target_entity.get_component(Crafter)
        assert inventory is not None
        assert crafter is not None

        item = inventory.inventory.pop(int(kwargs["inventory index"]))
        if not crafter.can_accept(item):
            raise ValueError(f"{target_entity.name} cannot accept {item.name}.")
        if "in_inventory" in item.tags:
            item.tags.remove("in_inventory")
        if item in env.state.entities:
            env.destroy_entity(item)
        crafter.load_item(item)
        return {"loaded_item": item.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Load an inventory item into {target_entity.name}."


def copy_position(position):
    from copy import deepcopy
    return deepcopy(position)


class Collect_From_Crafter(Action):
    """Collect the finished output from a Crafter directly into inventory."""

    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Crafter),
            ],
        )

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        if not super().is_valid(actor, target_entity, env, kwargs=kwargs):
            return False
        crafter = target_entity.get_component(Crafter)
        if crafter is None:
            return False
        return crafter.ready_recipe is not None

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        crafter = target_entity.get_component(Crafter)
        assert crafter is not None

        item = crafter.collect_output()
        inventory = actor.get_component(Inventory)
        if inventory is None:
            raise ValueError(f"{actor.name} has no inventory to collect the item into.")

        inventory.inventory.append(item)
        item.tags.add("in_inventory")
        if "collectable" not in item.tags:
            item.tags.add("collectable")

        return {"collected_item": item.name, "from": target_entity.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Collect the finished item from {target_entity.name}."
