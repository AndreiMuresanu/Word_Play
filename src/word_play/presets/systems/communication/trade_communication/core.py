from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from word_play.core import Entity, Environment
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory, inventory_items


@dataclass
class Trade_Offer:
    items: list[Entity] = field(default_factory=list)
    currency: float = 0
    request_text: str = ""

    @classmethod
    def from_kwargs(cls, actor: Entity, kwargs: dict | None) -> "Trade_Offer":
        kwargs = kwargs or {}
        raw_items = kwargs.get("offer_items", [])
        if isinstance(raw_items, str):
            raw_items = [part.strip() for part in raw_items.split(",") if part.strip()]
        elif raw_items is None:
            raw_items = []
        elif not isinstance(raw_items, list):
            raw_items = [raw_items]

        inventory = inventory_items(actor)
        items: list[Entity] = []
        for raw_idx in raw_items:
            try:
                item_index = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if 0 <= item_index < len(inventory):
                items.append(inventory[item_index])

        try:
            currency = float(kwargs.get("offer_currency", 0) or 0)
        except (TypeError, ValueError):
            currency = 0

        return cls(items=items, currency=max(0, currency), request_text=str(kwargs.get("request", "")))

    def __str__(self) -> str:
        parts = []
        if self.items:
            parts.append(", ".join(item.name for item in self.items))
        if self.currency > 0:
            parts.append(f"{self.currency:g} currency")
        return " and ".join(parts) or "nothing"


def _trade_offer_is_empty(offer: Trade_Offer | None) -> bool:
    return offer is None or (not offer.items and offer.currency <= 0 and not offer.request_text.strip())


def _trade_round_info(
    speaker: Entity,
    recipient: Entity,
    current_offers: dict[Entity, dict[Entity, Trade_Offer]],
    round_idx: int,
    trade_duration: int,
) -> str:
    outgoing = current_offers.get(speaker, {}).get(recipient) or Trade_Offer()
    incoming = current_offers.get(recipient, {}).get(speaker) or Trade_Offer()

    return (
        f"Trade round {round_idx + 1}/{trade_duration}. "
        f"Your current standing offer to {recipient.name}: {outgoing}. "
        f"{recipient.name}'s current offer to you: {incoming}. "
        "Make a revised proposal this round: add an item, remove an item, swap an item, or change currency. "
        "Only leave it empty if repeating your current standing offer is truly the best move."
    )


def _trade_message_info(
    speaker: Entity,
    recipient: Entity,
    current_offers: dict[Entity, dict[Entity, Trade_Offer]],
) -> str:
    outgoing = current_offers.get(speaker, {}).get(recipient) or Trade_Offer()
    incoming = current_offers.get(recipient, {}).get(speaker) or Trade_Offer()

    return (
        "This is a trade negotiation. "
        f"Your offer to {recipient.name}: {outgoing}. "
        f"{recipient.name}'s offer to you: {incoming}. "
        "Send one short message about the deal."
    )


class Trading_Policy(Communication_Policy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_trade = False

    def post_actions_step(self, env: Environment) -> None:
        self.in_trade = False

    @abstractmethod
    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    @abstractmethod
    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Trade_Offer:
        pass

    @abstractmethod
    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        pass

    @abstractmethod
    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


def _initial_offer_entities(
    participants: list[Entity],
    initial_offers: dict[Entity, dict[Entity, Trade_Offer]] | None,
) -> dict[Entity, dict[Entity, Trade_Offer]]:
    offers: dict[Entity, dict[Entity, Trade_Offer]] = {participant: {} for participant in participants}
    if not initial_offers:
        return offers

    for sender, recipient_offers in initial_offers.items():
        if sender not in offers:
            continue
        for recipient, offer in recipient_offers.items():
            if recipient not in offers or recipient is sender:
                continue
            if not _trade_offer_is_empty(offer):
                offers[sender][recipient] = offer

    return offers


def sim_simple_trade(
    participants: list[Entity],
    env: Environment,
    initial_offers: dict[Entity, dict[Entity, Trade_Offer]] | None = None,
    trade_duration: int = 3,
) -> dict[str, Any]:
    if len(participants) != 2:
        return {"error": "sim_simple_trade expects exactly two participants."}

    policies = {participant: participant.get_component(Trading_Policy) for participant in participants}
    if any(policy is None for policy in policies.values()):
        return {"error": "All trade participants need a Trading_Policy."}

    trade_info = f"Starting trade negotiation with {[participant.name for participant in participants]}."
    current_offers = _initial_offer_entities(participants, initial_offers)

    print(f"====== Starting trade with: {[participant.name for participant in participants]} ======")
    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            print(f"Initial offer from {sender.name} to {recipient.name}: {offer}")

    for participant, policy in policies.items():
        policy.in_trade = True
        policy.start_conversation(participants, env, trade_info)
        policy.start_trade(participants, env, trade_info)

    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            policies[recipient].receive_trade_offer(offer, sender, env)

    for round_idx in range(trade_duration):
        print(f"------ Trade round {round_idx + 1}/{trade_duration} ------")
        for speaker in participants:
            policy = policies[speaker]
            recipient = participants[1] if speaker is participants[0] else participants[0]
            recipients = [recipient]
            info = _trade_round_info(speaker, recipient, current_offers, round_idx, trade_duration)
            offer = policy.send_trade_offer(recipients, env, info)

            if not _trade_offer_is_empty(offer):
                current_offers[speaker][recipient] = offer
                print(f"Trade offer from {speaker.name} to {recipient.name}: {offer}")
                policies[recipient].receive_trade_offer(offer, speaker, env)

            message = policy.send_message(recipients, env, _trade_message_info(speaker, recipient, current_offers))
            print(f"{speaker.name}: {message}")
            policies[recipient].receive_message(message, speaker, env)

    transfer_offers: dict[tuple[Entity, Entity], Trade_Offer] = {}
    moved_items = set()
    for sender, recipient_offers in current_offers.items():
        sender_inventory = sender.get_component(Inventory)
        for recipient, offer in recipient_offers.items():
            recipient_inventory = recipient.get_component(Inventory)
            if sender_inventory is None or recipient_inventory is None:
                continue
            for item in offer.items:
                if item in moved_items or item not in sender_inventory.inventory:
                    continue
                sender_inventory.inventory.remove(item)
                if item in env.state.entities:
                    env.destroy_entity(item)
                item.position = recipient.position
                recipient_inventory.inventory.append(item)
                if "in_inventory" not in item.tags:
                    item.tags.append("in_inventory")
                if item not in env.state.entities:
                    env.instantiate_entity(item)
                transfer = transfer_offers.setdefault((sender, recipient), Trade_Offer())
                transfer.items.append(item)
                moved_items.add(item)

    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            sender_money = sender.get_component(Money)
            recipient_money = recipient.get_component(Money)
            moved_currency = (
                sender_money.transfer_to(recipient_money, offer.currency)
                if sender_money is not None and recipient_money is not None
                else 0
            )
            if moved_currency > 0:
                transfer = transfer_offers.setdefault((sender, recipient), Trade_Offer())
                transfer.currency += moved_currency

    transfers = [
        {
            "from": sender.name,
            "to": recipient.name,
            "items": [item.name for item in offer.items],
            "currency": offer.currency,
        }
        for (sender, recipient), offer in transfer_offers.items()
        if offer.items or offer.currency > 0
    ]

    summary = {"transfers": transfers}
    print("------ Trade settlement ------")
    if transfers:
        for transfer in transfers:
            items_text = ", ".join(transfer["items"]) if transfer["items"] else "no items"
            print(
                f"{transfer['from']} -> {transfer['to']}: "
                f"{items_text} and {transfer['currency']:g} currency"
            )
    else:
        print("No transfers.")
    for participant, policy in policies.items():
        policy.end_trade(participants, env, str(summary))
        policy.end_conversation(participants, env, str(summary))
        policy.in_trade = False

    print(f"====== Ending trade with: {[participant.name for participant in participants]} ======")
    return summary
