from __future__ import annotations

from typing import Any

from word_play.core import Entity, Environment
from word_play.presets.action_policies.llm_action_and_communication import (
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import (
    Human_Communication_Policy,
)
from word_play.presets.systems.communication.trade_communication.core import (
    Trade_Offer,
    Trading_Policy,
    inventory_items,
)
from word_play.presets.systems.currency import Money


def _money_text(entity: Entity) -> str:
    money = entity.get_component(Money)
    if money is None:
        return "none"
    return f"{money.amount:g} {money.currency_name}"


def _inventory_text(entity: Entity) -> str:
    items = inventory_items(entity)
    if not items:
        return "empty"
    return ", ".join(f"{idx}: {item.name}" for idx, item in enumerate(items))


def _offer_text(offer: Trade_Offer) -> str:
    parts = []
    if offer.items:
        parts.append(", ".join(item.name for item in offer.items))
    if offer.currency > 0:
        parts.append(f"{offer.currency:g} currency")
    return " and ".join(parts) or "nothing"


class LLM_Trading_Policy(LLM_Action_And_Communication_Policy, Trading_Policy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_trade = False

    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            self._trim_history()

    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Trade_Offer | dict[str, dict[str, Any]]:
        prompt = self._trade_offer_prompt(recipients, env, info)
        raw = self.model.generate_text(
            self._with_system(prompt),
            self.action_generation_config,
            max_new_tokens=self.action_max_new_tokens,
        ).strip()
        parsed = self._extract_json(raw)
        if len(recipients) <= 1:
            return self._offer_payload(parsed)
        return {
            recipient.name: self._offer_payload(parsed.get(recipient.name, {}))
            for recipient in recipients
        }

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        self.conversation_history.append(
            {
                "role": "system",
                "content": f"Trade offer from {sender.name}: {_offer_text(offer)}.",
            }
        )
        self._trim_history()

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            self._trim_history()

    def _trade_offer_prompt(self, recipients: list[Entity], env: Environment, info: str | None) -> str:
        recipient_names = ", ".join(entity.name for entity in recipients)
        recipient_blocks = []
        for recipient in recipients:
            recipient_blocks.append(
                f"{recipient.name}: inventory={_inventory_text(recipient)}; money={_money_text(recipient)}"
            )
        recipient_text = "\n".join(recipient_blocks) or "none"
        history = (
            "\n".join(entry["content"] for entry in self.conversation_history[-self.conversation_memory_window :])
            or "(no prior messages)"
        )
        info_text = f"\nTrade context: {info}\n" if info else ""

        if len(recipients) <= 1:
            output_format = '{"items": "comma-separated inventory indices or empty string", "currency": 0}'
        else:
            output_format = (
                '{"RecipientName": {"items": "comma-separated inventory indices or empty string", "currency": 0}}'
            )

        return (
            "You are negotiating a trade in a grid-world game.\n"
            "Choose what items from YOUR inventory and how much currency to offer.\n"
            "Each round should usually revise your standing offer: add something, remove something, swap an item, "
            "or change the currency amount in response to the negotiation. "
            "Avoid repeating the exact same offer twice unless no legal change improves your position. "
            "A blank item list and 0 currency means keep your current offer, so use that sparingly.\n\n"
            f"Your character: {self.entity.name}\n"
            f"Your inventory: {_inventory_text(self.entity)}\n"
            f"Your money: {_money_text(self.entity)}\n"
            f"Recipients: {recipient_names}\n"
            f"Recipient state:\n{recipient_text}\n"
            f"{info_text}"
            f"Recent negotiation:\n{history}\n\n"
            "Reply with ONLY a JSON object in this format:\n"
            f"{output_format}\n\n"
            "Your JSON:"
        )

    def _offer_payload(self, parsed: Any) -> dict[str, Any]:
        if not isinstance(parsed, dict):
            return {"items": [], "currency": 0}
        items = parsed.get("items", "")
        if isinstance(items, list):
            items = ", ".join(str(item) for item in items)
        try:
            currency = int(parsed.get("currency", 0) or 0)
        except (TypeError, ValueError):
            currency = 0
        return {"items": items, "currency": max(0, currency)}


class Human_Trading_Policy(Human_Communication_Policy, Trading_Policy):
    MAX_ATTEMPTS = 10

    def __init__(self):
        Trading_Policy.__init__(self)

    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            print(info)

    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Trade_Offer | dict[str, Trade_Offer]:
        if info:
            print(info)
        if len(recipients) <= 1:
            return self._terminal_offer(recipients[0] if recipients else None)
        return {recipient.name: self._terminal_offer(recipient) for recipient in recipients}

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        print(f"Trade offer from {sender.name}: {_offer_text(offer)}")

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            print(info)

    def _terminal_offer(self, recipient: Entity | None = None) -> Trade_Offer:
        recipient_text = f" to {recipient.name}" if recipient is not None else ""
        items = inventory_items(self.entity)
        print(f"Your inventory: {', '.join(f'{idx}: {item.name}' for idx, item in enumerate(items)) or 'empty'}")
        item_text = input(f"Item indices to offer{recipient_text}, comma-separated or blank: ")
        item_indices = self._parse_item_indices(item_text, len(items))
        money_amount = _money_amount(self.entity)
        currency_text = input(f"Currency to offer from 0 to {money_amount:g}: ")
        currency = self._parse_currency(currency_text, money_amount)
        return Trade_Offer(items=[items[idx] for idx in item_indices], currency=currency)

    def _parse_item_indices(self, text: str, item_count: int) -> list[int]:
        if not text.strip():
            return []
        indices = [int(part.strip()) for part in text.split(",") if part.strip()]
        if not all(0 <= idx < item_count for idx in indices):
            raise ValueError("Selected item index is outside your inventory.")
        return indices

    def _parse_currency(self, text: str, available: float) -> int:
        if not text.strip():
            return 0
        amount = int(text)
        if amount < 0 or amount > available:
            raise ValueError(f"Currency must be from 0 to {available:g}.")
        return amount


def _money_amount(entity: Entity) -> float:
    money = entity.get_component(Money)
    return 0 if money is None else money.amount


Simple_Trading_Policy = LLM_Trading_Policy
