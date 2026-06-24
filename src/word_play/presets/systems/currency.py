"""Currency system - Money component stores amount, renderer handles display.

Exports:
- Money: Component storing named currency amount
- Has_Money: Validation that entity has Money
- Has_Currency: Validation that amount > 0
- Currency_Amount_Arg: Action arg for currency amounts
"""
from __future__ import annotations

from word_play.core import Action_Validation, Component, Entity, Environment, Action_Arg


class Currency_Amount_Arg(Action_Arg):
    """Argument for selecting a currency amount."""
    def parse(self, input: str) -> int:
        return int(input)

    def is_valid(self, value: int | float, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        """Amount must be a positive number."""
        try:
            return value > 0
        except TypeError:
            return False

    def arg_description(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        money = actor.get_component(Money)
        if money:
            return f"Amount (you have {money.amount} {money.currency_name})"
        return "Amount"


class Money(Component):
    """Money component - just stores amount, renderer shows bill overlay."""

    def __init__(self, currency_name: str = "gold", amount: float = 0.0):
        super().__init__()
        self.currency_name = currency_name
        self.amount: float = amount

    def __str__(self) -> str:
        return f"{self.amount:g} {self.currency_name}"

    def add(self, amount: float) -> float:
        """Add amount, return actual added."""
        if amount <= 0:
            return 0.0
        self.amount += amount
        return amount

    def subtract(self, amount: float) -> float:
        """Subtract amount, return actual subtracted."""
        actual = min(amount, self.amount)
        self.amount -= actual
        return actual

    def transfer_to(self, recipient: Money, amount: float) -> float:
        """Move currency to another Money component, returning the amount moved."""
        moved = self.subtract(amount)
        recipient.add(moved)
        return moved


class Has_Money(Action_Validation):
    """Entity has Money component."""

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return actor.get_component(Money) is not None


class Has_Currency(Action_Validation):
    """Entity's money has positive amount (> 0)."""

    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        money = actor.get_component(Money)
        return money is not None and money.amount > 0


def money_amount(entity: Entity) -> float:
    """Currency held by an entity, or 0 if it has no Money component."""
    money = entity.get_component(Money)
    return 0 if money is None else money.amount


def amount_within_balance(amount: int | float, actor: Entity, target_entity: Entity, env: Environment) -> bool:
    """Action_Arg validator: amount is a non-bool number in [0, actor's balance]."""
    return isinstance(amount, (int, float)) and not isinstance(amount, bool) and 0 <= amount <= money_amount(actor)
