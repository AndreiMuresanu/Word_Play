from __future__ import annotations

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
)
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory, inventory_items


class LLM_Trading_Policy(LLM_Action_And_Communication_Policy, Trading_Policy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_trade = False

    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Trade_Offer:
        recipient = recipients[0] if recipients else None
        raw = self.model.generate_text(
            self._with_system(self._trade_offer_prompt(recipient, info)),
            self.action_generation_config,
            max_new_tokens=self.action_max_new_tokens,
        ).strip()
        payload = self._extract_json(raw)
        return Trade_Offer.from_kwargs(
            self.entity,
            {
                "offer_items": payload.get("items", []),
                "offer_currency": payload.get("currency", 0),
            },
        )

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        self.receive_message(f"Trade offer: {offer}", sender, env)

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def _trade_offer_prompt(self, recipient: Entity | None, info: str | None) -> str:
        recipient_inventory = recipient.get_component(Inventory) if recipient is not None else None
        recipient_money = recipient.get_component(Money) if recipient is not None else None
        info_text = f"\nTrade context: {info}\n" if info else ""
        return (
            "You are negotiating a trade in a grid-world game.\n"
            "Choose what items from YOUR inventory and how much currency to offer. "
            "A blank item list and 0 currency means keep your current offer.\n\n"
            f"Your character: {self.entity.name}\n"
            f"Your inventory: {self.entity.get_component(Inventory) or 'empty'}\n"
            f"Your money: {self.entity.get_component(Money) or 'none'}\n"
            f"Recipient: {recipient.name if recipient is not None else 'none'}\n"
            f"Recipient inventory: {recipient_inventory or 'empty'}\n"
            f"Recipient money: {recipient_money or 'none'}\n"
            f"{info_text}"
            f"{self._conversation_memory_block()}"
            "Reply with ONLY a JSON object in this format:\n"
            '{"items": "comma-separated inventory indices or empty string", "currency": 0}\n\n'
            "Your JSON:"
        )


class Human_Trading_Policy(Human_Communication_Policy, Trading_Policy):
    def __init__(self):
        super().__init__()

    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Trade_Offer:
        if info:
            print(info)
        return self._input_trade_offer(recipients[0] if recipients else None)

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        print(f"Received trade offer from {sender.name}: {offer}")

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def _input_trade_offer(self, recipient: Entity | None = None) -> Trade_Offer:
        recipient_text = f" to {recipient.name}" if recipient is not None else ""
        items = inventory_items(self.entity)
        print(f"Your inventory: {', '.join(f'{idx}: {item.name}' for idx, item in enumerate(items)) or 'empty'}")
        money = self.entity.get_component(Money)
        money_amount = 0 if money is None else money.amount
        offer_text = input(
            f"Offer{recipient_text} as 'item indices; currency' "
            f"(currency 0 to {money_amount:g}, blank for nothing): "
        )
        item_text, _, currency_text = offer_text.partition(";")
        item_indices = [int(part.strip()) for part in item_text.split(",") if part.strip()]
        if not all(0 <= idx < len(items) for idx in item_indices):
            raise ValueError("Selected item index is outside your inventory.")
        currency = float(currency_text.strip() or 0)
        if currency < 0 or currency > money_amount:
            raise ValueError(f"Currency must be from 0 to {money_amount:g}.")
        return Trade_Offer.from_kwargs(self.entity, {"offer_items": item_indices, "offer_currency": currency})
