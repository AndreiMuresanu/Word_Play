from __future__ import annotations

from typing import Any, Callable

from word_play.core import Action, Action_Arg, Action_Validation, Entity, Environment
from word_play.core.actions import Target_Is_Self
from word_play.presets.action_args import Int_Arg, List_Arg
from word_play.presets.systems.communication.trade_communication.core import (
    Trading_Policy,
    in_trade,
    sim_simple_trade,
)
from word_play.presets.systems.currency import amount_within_balance, money_amount
from word_play.presets.systems.inventory import inventory_items


# A trade-resolution function: (participants, env, *, trade_duration=...) -> result dict.
# Args are left open because concrete formats (e.g. sim_simple_trade) accept extra optional kwargs.
Trade_Format = Callable[..., dict[str, Any]]


def nearby_trade_partners(actor: Entity, env: Environment) -> list[Entity]:
    return [
        entity
        for entity in env.state.entities
        if (
            entity is not actor
            and env.movement_system.positions_are_close(actor.position, entity.position)
            and entity.has_component(Trading_Policy)
            and not in_trade(entity)
        )
    ]


def _item_indices_are_valid(item_indices: list[int], actor: Entity, target_entity: Entity, env: Environment) -> bool:
    items = inventory_items(actor)
    return all(0 <= idx < len(items) for idx in item_indices)


def _partner_indices_are_valid(
    partner_indices: list[int],
    actor: Entity,
    target_entity: Entity,
    env: Environment,
) -> bool:
    partners = nearby_trade_partners(actor, env)
    return all(0 <= idx < len(partners) for idx in partner_indices)


class Actor_Has_Trading_Policy(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return actor.has_component(Trading_Policy)


class Not_In_Trade(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return not in_trade(actor) and not in_trade(target_entity)


class A_Trade_Partner_Is_Nearby(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return len(nearby_trade_partners(actor, env)) != 0


class Trade_Item_Indices(List_Arg):
    def __init__(self):
        super().__init__(Int_Arg(), validators=[_item_indices_are_valid])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        items = inventory_items(actor)
        items_text = ", ".join(f"{idx} ({item.name})" for idx, item in enumerate(items))
        return f"list of inventory item indices to offer: {items_text}"


class Trade_Currency_Amount(Action_Arg):
    def __init__(self):
        super().__init__(validators=[amount_within_balance])

    def parse(self, input: str) -> float:
        text = input.strip()
        return float(text) if text else 0.0

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"currency amount to offer, from 0 to {money_amount(actor):g}"


class Nearby_Trade_Partner_Indices(List_Arg):
    def __init__(self):
        super().__init__(Int_Arg(), validators=[_partner_indices_are_valid])

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        partners = nearby_trade_partners(actor, env)
        partners_text = ", ".join(f"{idx} ({entity.name})" for idx, entity in enumerate(partners))
        return f"list of indices representing the trade participants: {partners_text}"


class Start_Private_Trade(Action):
    def __init__(
        self,
        trade_format: Trade_Format = sim_simple_trade,
        trade_duration: int = 3,
    ):
        self.trade_format = trade_format
        self.trade_duration = trade_duration
        super().__init__(
            validation_rules=[
                Actor_Has_Trading_Policy(),
                Target_Is_Self(),
                Not_In_Trade(),
                A_Trade_Partner_Is_Nearby(),
            ],
            required_kwargs={"trade partners": Nearby_Trade_Partner_Indices()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert kwargs is not None and "trade partners" in kwargs, "Action missing kwarg: 'trade partners'"
        potential_participants = nearby_trade_partners(actor, env)
        participants = [potential_participants[idx] for idx in kwargs["trade partners"]]
        participants.append(actor)
        return self.trade_format(participants, env, trade_duration=self.trade_duration)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Start a private trade with only some of the nearby people."
