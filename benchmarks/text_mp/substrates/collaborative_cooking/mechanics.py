from __future__ import annotations

from word_play.core import Action, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Component
from word_play.presets.systems.crafter import Crafter
from word_play.presets.systems.inventory import Inventory

from benchmarks.text_mp.core.timing import normalized_steps


COOKING_TIME = normalized_steps(20)
COOKING_DELIVERY_REWARD = 20.0


def collaborative_cooking_events(env: Environment) -> list[str]:
    if getattr(env, "_collaborative_cooking_events_step", None) != env.cur_step:
        env.collaborative_cooking_events = []
        env._collaborative_cooking_events_step = env.cur_step
    return env.collaborative_cooking_events


class Plate_Ready_Soup_With_Dish(Action):
    """Use a held Dish to collect ready Soup from a Cooking Pot."""

    def __init__(self):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Component(Crafter),
            ]
        )

    def is_valid(self, actor, target, env, kwargs="unconsidered") -> bool:
        if not super().is_valid(actor, target, env, kwargs=kwargs):
            return False
        inventory = actor.get_component(Inventory)
        crafter = target.get_component(Crafter)
        return (
            inventory is not None
            and crafter is not None
            and crafter.ready_item is not None
            and "soup" in crafter.ready_item.tags
            and inventory.first_index_with_tags("dish") is not None
        )

    def exec_action(self, actor, target, env, kwargs=None):
        inventory = actor.get_component(Inventory)
        crafter = target.get_component(Crafter)
        dish_idx = inventory.first_index_with_tags("dish")
        dish = inventory.remove_by_index(dish_idx)
        if dish in env.state.entities:
            env.destroy_entity(dish)
        soup = crafter.collect_output()
        inventory.store(soup, env)
        collaborative_cooking_events(env).append(
            f"{actor.name} plated soup from {target.name}."
        )
        return {"success": True, "plated": soup.name, "used": "Dish", "from": target.name}

    def action_description_text(self, actor, target, env) -> str:
        return f"Use held Dish to collect ready Soup from {target.name}."
