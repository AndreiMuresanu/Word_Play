from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.core.movement import Position
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.inventory import Inventory, Inventory_Item_Index_Arg, materialize_item
from word_play.presets.renderers import Renderable
from copy import deepcopy


@dataclass(slots=True)
class Crafter_Recipe:
    input_names: tuple[str, ...]
    output: Entity | Callable[[], Entity]
    duration: int = 0


class _Ready_Recipe_Proxy:
    """Proxy object that provides .output attribute for ready recipe check."""

    def __init__(self, output_entity: Entity):
        self.output = output_entity


class Crafter(Component):
    """A crafter that acts as a container - items are loaded in, processed, and collected out."""

    def __init__(self, recipes: list[Crafter_Recipe]):
        super().__init__(actions=[Load_Crafter(), Collect_From_Crafter()])
        self.recipes = recipes
        self.staged_inputs: list[str] = []  # Track what's loaded for recipe matching
        self.active_recipe: Crafter_Recipe | None = None
        self.remaining_steps: int | None = None
        # Container holds the item currently being processed or the output
        self.stored_item: Entity | None = None
        self.stored_input_items: list[Entity] = []  # Keep reference to input items

    def can_accept(self, item: Entity) -> bool:
        # Can accept if not currently crafting and stored_item is empty
        if self.stored_item is not None:
            return False

        next_inputs = self.staged_inputs + [item.name]
        return any(self._matches_partial(recipe, next_inputs) for recipe in self.recipes)

    def load_item(self, item: Entity, container_position: Position | None = None) -> None:
        """Load item into the crafter container."""
        self.staged_inputs.append(item.name)
        self.stored_input_items.append(item)
        # Store container position for output positioning
        self._container_position = container_position
        # Update item position to container position
        if container_position is not None and item.position is not None:
            item.position = deepcopy(container_position)

        # Check if this completes a recipe
        for recipe in self.recipes:
            if sorted(self.staged_inputs) == sorted(recipe.input_names):
                self.active_recipe = recipe
                if recipe.duration <= 0:
                    # Instant craft - produce output immediately
                    self._produce_output()
                else:
                    # Start crafting
                    self.remaining_steps = recipe.duration
                return

    def _produce_output(self) -> None:
        """Produce the output and store it in the container."""
        if self.active_recipe is None:
            return
        output = materialize_item(self.active_recipe.output)
        # Set position of output to container position if stored
        if hasattr(self, '_container_position') and self._container_position is not None and output.position is not None:
            output.position = deepcopy(self._container_position)
        self.stored_item = output
        self.active_recipe = None
        self.remaining_steps = None
        self.staged_inputs = []
        self.stored_input_items = []

    def advance(self, env: Environment | None = None) -> bool:
        """Advance crafting by one step."""
        if self.remaining_steps is None or self.active_recipe is None:
            return False

        self.remaining_steps -= 1
        if self.remaining_steps <= 0:
            self._produce_output()
            return True
        return False

    def post_actions_step(self, env: Environment) -> None:
        self.advance(env)

    def has_output(self) -> bool:
        """Check if crafter has output ready to collect."""
        return self.stored_item is not None

    @property
    def ready_recipe(self) -> Crafter_Recipe | None:
        """Return a recipe-like object with output when crafting is complete."""
        if self.stored_item is None:
            return None

        # Create a recipe-like object that returns the stored item
        return _Ready_Recipe_Proxy(self.stored_item)

    @property
    def loaded_items(self) -> list[str]:
        """Return list of item names currently loaded in the crafter."""
        return list(self.staged_inputs)

    def collect_output(self) -> Entity:
        """Take the output from the container."""
        if self.stored_item is None:
            raise ValueError("Crafter has no output to collect.")
        item = self.stored_item
        self.stored_item = None
        self.staged_inputs = []
        self.stored_input_items = []
        self.active_recipe = None
        self.remaining_steps = None
        # Remove in_container tag so item renders normally again
        if "in_container" in item.tags:
            item.tags.remove("in_container")
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
    """Load an item into the crafter's container."""
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
        if kwargs is None or kwargs == "unconsidered":
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

        # Remove from inventory
        item = inventory.inventory.pop(int(kwargs["inventory index"]))
        if "in_inventory" in item.tags:
            item.tags.remove("in_inventory")

        # Load into crafter container with entity position
        crafter.load_item(item, target_entity.position)

        # Mark item as "in_container" so it won't render separately
        # (the crafter will render it as an overlay instead)
        if "in_container" not in item.tags:
            item.tags.append("in_container")

        return {"loaded_item": item.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Load an inventory item into {target_entity.name}."


class Collect_From_Crafter(Action):
    """Collect the output from a crafter's container."""
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
        # Can collect if there's output ready
        return crafter.has_output()

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        crafter = target_entity.get_component(Crafter)
        assert crafter is not None

        # Collect from container
        item = crafter.collect_output()
        inventory = actor.get_component(Inventory)
        if inventory is None:
            raise ValueError(f"{actor.name} has no inventory to collect the item into.")

        # Put in inventory
        inventory.inventory.append(item)
        item.tags.append("in_inventory")
        # Remove in_container tag so item renders normally again
        if "in_container" in item.tags:
            item.tags.remove("in_container")
        if "collectable" not in item.tags:
            item.tags.append("collectable")

        return {"collected_item": item.name, "from": target_entity.name}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Collect the finished item from {target_entity.name}."


