from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from word_play.core import Action, Component, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.inventory import In_Actor_Inventory, Inventory


class Consumable(Component):

    def __init__(self, on_consume: Callable[[Entity, Entity, Environment], None]):
        """on_consume(actor, consumed_entity, env) — apply the effect of consuming this entity."""
        super().__init__()
        self._on_consume = on_consume

    def on_consume(self, actor: Entity, consumed_entity: Entity, env: Environment) -> None:
        self._on_consume(actor, consumed_entity, env)


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

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        target_entity.get_component(Consumable).on_consume(actor, target_entity, env)
        inventory = actor.get_component(Inventory)
        inventory.inventory.remove(target_entity)
        target_entity.tags.remove("in_inventory")
        env.destroy_entity(target_entity)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Consume {target_entity.name}."
