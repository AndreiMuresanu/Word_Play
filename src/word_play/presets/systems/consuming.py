from __future__ import annotations

from typing import Callable

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import In_Actor_Inventory, Inventory

Consume_Effect = Callable[[Entity, Entity, Environment], None]


# Preset effects

def heal(amount: float) -> Consume_Effect:
    def effect(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        h = actor.get_component(Health)
        h.health = min(h.health + amount, h.max_health)
    return effect


def damage(amount: float) -> Consume_Effect:
    def effect(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        actor.get_component(Health).health -= amount
    return effect


def full_heal() -> Consume_Effect:
    def effect(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        h = actor.get_component(Health)
        h.health = h.max_health
    return effect


# Lifecycle effects

def _remove_from_inventory(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
    actor.get_component(Inventory).inventory.remove(consumed_entity)
    consumed_entity.tags.remove("in_inventory")
    env.destroy_entity(consumed_entity)


def destroy_item() -> Consume_Effect:
    """Lifecycle effect: remove the item from inventory and destroy it immediately."""
    def effect(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        _remove_from_inventory(actor, consumed_entity, env)
    return effect


def use_charge() -> Consume_Effect:
    """Lifecycle effect: decrement Item_Charge.count; destroy the item when charges reach zero."""
    def effect(actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        charge = consumed_entity.get_component(Item_Charge)
        charge.count -= 1
        if charge.count <= 0:
            _remove_from_inventory(actor, consumed_entity, env)
    return effect


# Components

class Item_Charge(Component):
    """Tracks how many uses an item has remaining. Pair with use_charge() in Consumable effects."""

    def __init__(self, count: int):
        assert count >= 1, "count must be at least 1"
        super().__init__()
        self.count = count


class Consumable(Component):

    def __init__(self, on_consume: Consume_Effect | list[Consume_Effect]):
        """on_consume: one effect or a list applied in order when the item is consumed."""
        super().__init__()
        self._effects: list[Consume_Effect] = on_consume if isinstance(on_consume, list) else [on_consume]

    def on_consume(self, actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        for effect in self._effects:
            effect(actor, consumed_entity, env)


# Actions

class Consume(Action):

    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                In_Actor_Inventory(),
                Target_Has_Component(Consumable),
            ]
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, _kwargs: dict | None) -> dict | None:
        target_entity.get_component(Consumable).on_consume(actor, target_entity, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        charge = target_entity.get_component(Item_Charge)
        if charge is not None and charge.count > 1:
            return f"Consume {target_entity.name} ({charge.count} uses remaining)."
        return f"Consume {target_entity.name}."
