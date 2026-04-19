from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Callable

from word_play.core import Action, Entity, Environment, Target_Is_Nearby, Target_Not_Self
from word_play.presets.action_validations import Target_Has_Tag
from word_play.presets.systems.inventory import Inventory, Inventory_Item_Index_Arg


class Any_Item_Valid:
    """Item validator that accepts any item."""

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, item: Entity) -> bool:
        return True


class Zero_Reward:
    """Reward function that always returns 0."""

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, item: Entity) -> float:
        return 0.0


@dataclass(slots=True)
class Front_Order_Match:
    order_attr: str = "order_queue"

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, item: Entity) -> bool:
        order_queue = getattr(env, self.order_attr, None)
        return isinstance(order_queue, Sequence) and bool(order_queue) and item.name == order_queue[0]

@dataclass(slots=True)
class Named_Item_Reward:
    rewards_by_name: dict[str, float]
    default_reward: float = 0.0

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, item: Entity) -> float:
        return float(self.rewards_by_name.get(item.name, self.default_reward))

@dataclass(slots=True)
class Record_Delivery:
    score_attr: str = "score"
    step_score_attr: str | None = "step_score_delta"
    count_attr: str | None = None
    order_attr: str | None = "order_queue"
    log_attr: str | None = None
    log_limit: int | None = None
    message_builder: Callable[[Entity, Entity, Environment, Entity, float], str] | None = None

    def __call__(self, actor: Entity, target_entity: Entity, env: Environment, item: Entity, reward: float) -> None:
        setattr(env, self.score_attr, int(getattr(env, self.score_attr, 0)) + int(reward))
        if self.step_score_attr is not None:
            setattr(env, self.step_score_attr, int(getattr(env, self.step_score_attr, 0)) + int(reward))
        if self.count_attr is not None:
            setattr(env, self.count_attr, int(getattr(env, self.count_attr, 0)) + 1)
        if self.order_attr is not None:
            order_queue = getattr(env, self.order_attr, None)
            if isinstance(order_queue, list) and order_queue:
                order_queue.pop(0)
        if self.log_attr is not None:
            existing_log = list(getattr(env, self.log_attr, []))
            message = (
                self.message_builder(actor, target_entity, env, item, reward)
                if self.message_builder is not None
                else f"{actor.name} delivered {item.name.replace('_', ' ')}."
            )
            updated_log = [message, *existing_log]
            setattr(env, self.log_attr, updated_log if self.log_limit is None else updated_log[:self.log_limit])


class Deliver_Item(Action):
    def __init__(
        self,
        target_tags: list[str],
        item_is_valid: Callable[[Entity, Entity, Environment, Entity], bool] | None = None,
        reward_for_item: Callable[[Entity, Entity, Environment, Entity], float] | None = None,
        on_delivered: Callable[[Entity, Entity, Environment, Entity, float], None] | None = None,
    ):
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Target_Has_Tag(target_tags),
            ],
            required_kwargs={"inventory index": Inventory_Item_Index_Arg()},
        )
        self.target_tags = target_tags
        self.item_is_valid = item_is_valid or Any_Item_Valid()
        self.reward_for_item = reward_for_item or Zero_Reward()
        self.on_delivered = on_delivered

    def is_valid(
        self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None | str = "unconsidered"
    ) -> bool:
        if not super().is_valid(actor, target_entity, env, kwargs=kwargs):
            return False
        inventory = actor.get_component(Inventory)
        if inventory is None:
            return False
        if kwargs == "unconsidered" or kwargs is None:
            return True
        item = inventory.inventory[int(kwargs["inventory index"])]
        return self.item_is_valid(actor, target_entity, env, item)

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None
        inventory = actor.get_component(Inventory)
        assert inventory is not None

        item = inventory.inventory.pop(int(kwargs["inventory index"]))
        if "in_inventory" in item.tags:
            item.tags.remove("in_inventory")
        if item in env.state.entities:
            env.destroy_entity(item)

        reward = float(self.reward_for_item(actor, target_entity, env, item))
        if self.on_delivered is not None:
            self.on_delivered(actor, target_entity, env, item, reward)

        return {"delivered_item": item.name, "reward": reward}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Deliver an inventory item to {target_entity.name}."
