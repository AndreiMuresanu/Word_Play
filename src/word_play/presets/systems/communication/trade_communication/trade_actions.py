from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from word_play.core import Action, Action_Arg, Action_Validation, Component, Entity, Environment
from word_play.core.actions import Target_Is_Nearby, Target_Is_Self, Target_Not_Self
from word_play.presets.action_args import Int_Arg, List_Arg, String_Arg
from word_play.presets.systems.communication.trade_communication.core import (
    Trade_Offer,
    Trading_Policy,
    in_trade,
    inventory_items,
    sim_simple_trade,
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory


Trade_Format = Callable[..., dict | None]


def has_active_public_trade_offer(entity: Entity) -> bool:
    offer = entity.get_component(Public_Trade_Offer)
    return bool(offer is not None and offer.active)


def nearby_trade_partners(actor: Entity, env: Environment) -> list[Entity]:
    if has_active_public_trade_offer(actor):
        return []
    return [
        entity
        for entity in env.state.entities
        if (
            entity is not actor
            and env.movement_system.positions_are_close(actor.position, entity.position)
            and entity.has_component(Trading_Policy)
            and not in_trade(entity)
            and not has_active_public_trade_offer(entity)
        )
    ]


def public_trade_offer_targets(actor: Entity, env: Environment) -> list[Entity]:
    if has_active_public_trade_offer(actor):
        return []
    return [
        entity
        for entity in env.state.entities
        if (
            entity is not actor
            and env.movement_system.positions_are_close(actor.position, entity.position)
            and entity.has_component(Trading_Policy)
            and not in_trade(entity)
            and has_active_public_trade_offer(entity)
        )
    ]


def _actor_money_amount(actor: Entity) -> float:
    money = actor.get_component(Money)
    return 0 if money is None else money.amount


def _selected_public_offer_this_step(actor: Entity, env: Environment) -> bool:
    for selection in getattr(env, "_current_step_action_selections", []) or []:
        if selection.actor is actor:
            continue
        if isinstance(selection.action, Start_Public_Trade):
            return True
    return False


def _item_indices_are_valid(item_indices: list[int], actor: Entity, target_entity: Entity, env: Environment) -> bool:
    items = inventory_items(actor)
    return all(0 <= idx < len(items) for idx in item_indices)


def _currency_amount_is_valid(amount: int | float, actor: Entity, target_entity: Entity, env: Environment) -> bool:
    return isinstance(amount, (int, float)) and not isinstance(amount, bool) and 0 <= amount <= _actor_money_amount(actor)


def _partner_indices_are_valid(
    partner_indices: list[int],
    actor: Entity,
    target_entity: Entity,
    env: Environment,
) -> bool:
    partners = nearby_trade_partners(actor, env)
    return all(0 <= idx < len(partners) for idx in partner_indices)


def _offer_from_kwargs(actor: Entity, kwargs: dict | None) -> Trade_Offer:
    kwargs = kwargs or {}
    items = inventory_items(actor)
    offer_items = [items[idx] for idx in kwargs.get("offer items", []) if 0 <= idx < len(items)]
    return Trade_Offer(
        items=offer_items,
        currency=float(kwargs.get("offer currency", 0) or 0),
        request_text=str(kwargs.get("request", "")),
    )


def _format_offer_items(items: list[Entity]) -> str:
    return str([item.name for item in items])


def _format_public_offer(offer: "Public_Trade_Offer") -> str:
    request = offer.request_text or "anything"
    return f"{_format_offer_items(offer.items)} and {offer.currency:g} currency for {request}"


class Not_In_Trade(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return not in_trade(actor) and not in_trade(target_entity)


class No_Active_Public_Trade_Offer(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return not has_active_public_trade_offer(actor)


class No_Other_Public_Trade_Offer_Selected_This_Step(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return not _selected_public_offer_this_step(actor, env)


class A_Trade_Partner_Is_Nearby(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return len(nearby_trade_partners(actor, env)) != 0


class Public_Trade_Offer_Is_Available(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return target_entity in public_trade_offer_targets(actor, env)


class Trade_Item_Indices(List_Arg):
    def __init__(self):
        super().__init__(Int_Arg(), validators=[_item_indices_are_valid])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        items = inventory_items(actor)
        items_text = ", ".join(f"{idx} ({item.name})" for idx, item in enumerate(items))
        return f"list of inventory item indices to offer: {items_text}"


class Trade_Currency_Amount(Action_Arg):
    def __init__(self):
        super().__init__(validators=[_currency_amount_is_valid])

    def parse(self, input: str) -> int:
        text = input.strip()
        if not text:
            return 0
        return int(text)

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"currency amount to offer, from 0 to {_actor_money_amount(actor):g}"


class Nearby_Trade_Partner_Indices(List_Arg):
    def __init__(self):
        super().__init__(Int_Arg(), validators=[_partner_indices_are_valid])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        partners = nearby_trade_partners(actor, env)
        partners_text = ", ".join(f"{idx} ({entity.name})" for idx, entity in enumerate(partners))
        return f"list of indices representing the trade participants: {partners_text}"


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
            inventory = owner.get_component(Inventory)
            if inventory is not None:
                for item in offer.items:
                    inventory.remove(item)

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
            inventory = owner.get_component(Inventory)
            if inventory is not None:
                for item in self.items:
                    inventory.store(item, env)

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


class Start_Public_Trade(Action):
    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self(), Not_In_Trade(), No_Active_Public_Trade_Offer()],
            required_kwargs={
                "offer items": Trade_Item_Indices(),
                "offer currency": Trade_Currency_Amount(),
                "request": String_Arg(),
            },
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        public_offer = actor.get_component(Public_Trade_Offer)
        if public_offer is None:
            public_offer = Public_Trade_Offer()
            public_offer.entity = actor
            actor.components[Public_Trade_Offer] = public_offer

        offer = _offer_from_kwargs(actor, kwargs)
        public_offer.post_offer(offer, env)
        policy = actor.get_component(Trading_Policy)
        if policy is not None:
            policy.in_trade = True
        return {"public_trade_offer": _format_public_offer(public_offer)}

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
                No_Other_Public_Trade_Offer_Selected_This_Step(),
                Public_Trade_Offer_Is_Available(),
            ],
            required_kwargs={
                "offer items": Trade_Item_Indices(),
                "offer currency": Trade_Currency_Amount(),
            },
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        public_offer = target_entity.get_component(Public_Trade_Offer)
        if public_offer is None or not public_offer.active:
            return None

        accepted_offer = public_offer.take_offer(env)
        counter_offer = _offer_from_kwargs(actor, kwargs)
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
        return f"Accept {target_entity.name}'s public trade offer: {_format_public_offer(public_offer)}."


class Start_Private_Trade(Action):
    def __init__(
        self,
        trade_format: Trade_Format = sim_simple_trade,
    ):
        self.trade_format = trade_format
        super().__init__(
            validation_rules=[
                Target_Is_Self(),
                Not_In_Trade(),
                No_Active_Public_Trade_Offer(),
                No_Other_Public_Trade_Offer_Selected_This_Step(),
                A_Trade_Partner_Is_Nearby(),
            ],
            required_kwargs={"trade partners": Nearby_Trade_Partner_Indices()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None and "trade partners" in kwargs, "Action missing kwarg: 'trade partners'"
        potential_participants = nearby_trade_partners(actor, env)
        participants = [potential_participants[idx] for idx in kwargs["trade partners"]]
        participants.append(actor)
        return self.trade_format(participants, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Start a private trade with only some of the nearby people."
