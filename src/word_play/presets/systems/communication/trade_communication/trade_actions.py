from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from word_play.core import Action, Action_Arg, Action_Validation, Component, Entity, Environment
from word_play.core.actions import Target_Is_Nearby, Target_Is_Self, Target_Not_Self
from word_play.presets.action_args import String_Arg
from word_play.presets.systems.communication.trade_communication.core import (
    Trade_Offer,
    Trading_Policy,
    sim_simple_trade,
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory, inventory_items


Trade_Format = Callable[..., dict | None]


class Not_In_Trade(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        actor_policy = actor.get_component(Trading_Policy)
        target_policy = target_entity.get_component(Trading_Policy)
        return not (actor_policy is not None and actor_policy.in_trade) and not (
            target_policy is not None and target_policy.in_trade
        )


class No_Active_Public_Trade_Offer(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        public_offer = actor.get_component(Public_Trade_Offer)
        return public_offer is None or not public_offer.active


class Private_Trade_Partner_Is_Available(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        public_offer = target_entity.get_component(Public_Trade_Offer)
        return target_entity.has_component(Trading_Policy) and (public_offer is None or not public_offer.active)


class Public_Trade_Offer_Is_Available(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        public_offer = target_entity.get_component(Public_Trade_Offer)
        return target_entity.has_component(Trading_Policy) and public_offer is not None and public_offer.active


class Trade_Item_Indices(Action_Arg):
    def __init__(self):
        super().__init__()

    def parse(self, input: str | list[int | str]) -> list[int]:
        if isinstance(input, list):
            return [int(item) for item in input]
        text = input.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [int(part.strip()) for part in text.split(",") if part.strip()]

    def is_valid(self, arg: list[int], actor: Entity, target_entity: Entity, env: Environment) -> bool:
        if not isinstance(arg, list):
            return False
        items = inventory_items(actor)
        return all(isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(items) for idx in arg)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        items = inventory_items(actor)
        items_text = ", ".join(f"{idx} ({item.name})" for idx, item in enumerate(items))
        return f"list of inventory item indices to offer: {items_text}"


class Trade_Currency_Amount(Action_Arg):
    def __init__(self):
        super().__init__()

    def parse(self, input: str) -> float:
        text = input.strip()
        if not text:
            return 0.0
        return float(text)

    def is_valid(self, arg: int | float, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        money = actor.get_component(Money)
        money_amount = 0 if money is None else money.amount
        return isinstance(arg, (int, float)) and not isinstance(arg, bool) and 0 <= arg <= money_amount

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        money = actor.get_component(Money)
        money_amount = 0 if money is None else money.amount
        return f"currency amount to offer, from 0 to {money_amount:g}"


@dataclass
class Public_Trade_Offer(Component):
    items: list[Entity] = field(default_factory=list)
    currency: float = 0
    request_text: str = ""
    active: bool = False
    posted_step: int | None = None

    def __post_init__(self) -> None:
        Component.__init__(self)

    def clear(self) -> None:
        self.items = []
        self.currency = 0
        self.request_text = ""
        self.active = False
        self.posted_step = None

    def post_offer(self, offer: Trade_Offer, env: Environment | None = None) -> None:
        if self.active:
            self.refund(env)

        owner = self.entity
        if owner is not None:
            owner_inventory = owner.get_component(Inventory)
            if owner_inventory is not None:
                for item in offer.items:
                    if item in owner_inventory.inventory:
                        owner_inventory.inventory.remove(item)
                        if env is not None and item in env.state.entities:
                            env.destroy_entity(item)

            money = owner.get_component(Money)
            if money is not None and offer.currency > 0:
                offer.currency = money.subtract(offer.currency)

        self.items = list(offer.items)
        self.currency = offer.currency
        self.request_text = offer.request_text
        self.active = bool(self.items or self.currency > 0 or self.request_text.strip())
        self.posted_step = getattr(env, "cur_step", None) if env is not None else None

    def refund(self, env: Environment | None = None) -> None:
        if not self.active:
            return
        owner = self.entity
        if owner is not None:
            owner_inventory = owner.get_component(Inventory)
            if owner_inventory is not None:
                for item in self.items:
                    if item in owner_inventory.inventory:
                        continue
                    item.position = owner.position
                    owner_inventory.inventory.append(item)
                    if "in_inventory" not in item.tags:
                        item.tags.append("in_inventory")
                    if env is not None and item not in env.state.entities:
                        env.instantiate_entity(item)

            money = owner.get_component(Money)
            if money is not None and self.currency > 0:
                money.add(self.currency)

        self.clear()

    def take_offer(self, env: Environment | None = None) -> Trade_Offer:
        offer = Trade_Offer(list(self.items), self.currency, self.request_text)
        self.refund(env)
        return offer

    def post_actions_step(self, env: Environment) -> None:
        if self.active and self.posted_step is not None and env.cur_step > self.posted_step:
            self.refund(env)

    def __str__(self) -> str:
        request = self.request_text or "anything"
        offered = str(Trade_Offer(items=self.items, currency=self.currency))
        return f"{offered} for {request}"


class Start_Public_Trade(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self(), Not_In_Trade(), No_Active_Public_Trade_Offer()],
            required_kwargs={
                "offer_items": Trade_Item_Indices(),
                "offer_currency": Trade_Currency_Amount(),
                "request": String_Arg(),
            },
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        public_offer = actor.get_component(Public_Trade_Offer)
        if public_offer is None:
            public_offer = Public_Trade_Offer()
            public_offer.entity = actor
            actor.components[Public_Trade_Offer] = public_offer

        offer = Trade_Offer.from_kwargs(actor, kwargs)
        public_offer.post_offer(offer, env)
        policy = actor.get_component(Trading_Policy)
        if policy is not None:
            policy.in_trade = True
        return {"public_trade_offer": str(public_offer)}

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Post a public trade offer."


class Accept_Public_Trade(Action):
    def __init__(
        self,
        trade_format: Trade_Format = sim_simple_trade,
    ):
        self.trade_format = trade_format
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Not_In_Trade(),
                No_Active_Public_Trade_Offer(),
                Public_Trade_Offer_Is_Available(),
            ],
            required_kwargs={
                "offer_items": Trade_Item_Indices(),
                "offer_currency": Trade_Currency_Amount(),
            },
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        public_offer = target_entity.get_component(Public_Trade_Offer)
        if public_offer is None or not public_offer.active:
            return None

        accepted_offer = public_offer.take_offer(env)
        counter_offer = Trade_Offer.from_kwargs(actor, kwargs)
        participants = [target_entity, actor]
        return self.trade_format(
            participants,
            env,
            initial_offers={
                target_entity: {actor: accepted_offer},
                actor: {target_entity: counter_offer},
            },
        )

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        public_offer = target_entity.get_component(Public_Trade_Offer)
        if public_offer is None:
            return f"Accept {target_entity.name}'s public trade offer."
        return f"Accept {target_entity.name}'s public trade offer: {public_offer}."


class Start_Private_Trade(Action):
    def __init__(
        self,
        trade_format: Trade_Format = sim_simple_trade,
    ):
        self.trade_format = trade_format
        super().__init__(
            validation_rules=[
                Target_Not_Self(),
                Target_Is_Nearby(),
                Not_In_Trade(),
                No_Active_Public_Trade_Offer(),
                Private_Trade_Partner_Is_Available(),
            ],
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        return self.trade_format([target_entity, actor], env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Start a private trade with {target_entity.name}."
