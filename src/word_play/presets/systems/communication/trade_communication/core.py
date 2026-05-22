from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from word_play.core import Entity, Environment
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory


@dataclass
class Trade_Offer:
    items: list[Entity] = field(default_factory=list)
    currency: float = 0
    request_text: str = ""


def inventory_items(entity: Entity) -> list[Entity]:
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return []
    return list(inventory.inventory)


def can_receive_trade_items(entity: Entity, count: int = 1) -> bool:
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return False
    return inventory.inventory_size < 0 or len(inventory.inventory) + count <= inventory.inventory_size


def _remove_item(entity: Entity, item: Entity) -> Entity | None:
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return None
    return inventory.remove(item)


def _add_item(entity: Entity, item: Entity, env: Environment) -> bool:
    inventory = entity.get_component(Inventory)
    if inventory is None:
        return False
    return inventory.store(item, env)


def _move_currency(sender: Entity, recipient: Entity, amount: float) -> float:
    if amount <= 0:
        return 0
    sender_money = sender.get_component(Money)
    recipient_money = recipient.get_component(Money)
    if sender_money is None or recipient_money is None:
        return 0
    moved = sender_money.subtract(amount)
    recipient_money.add(moved)
    return moved


def _trade_offer_is_empty(offer: Trade_Offer | None) -> bool:
    return offer is None or (not offer.items and offer.currency <= 0 and not offer.request_text.strip())


def _trade_offer_text(offer: Trade_Offer | None) -> str:
    if offer is None or (not offer.items and offer.currency <= 0):
        return "nothing"
    parts = []
    if offer.items:
        parts.append(", ".join(item.name for item in offer.items))
    if offer.currency > 0:
        parts.append(f"{offer.currency:g} currency")
    return " and ".join(parts)


def _offer_from_payload(payload: Any, sender: Entity, recipient: Entity | None = None) -> Trade_Offer:
    if isinstance(payload, Trade_Offer):
        return payload
    if not isinstance(payload, dict):
        return Trade_Offer()

    if recipient is not None and recipient.name in payload and "items" not in payload:
        return _offer_from_payload(payload[recipient.name], sender, recipient)

    raw_items = payload.get("items", [])
    if isinstance(raw_items, str):
        indices = [part.strip() for part in raw_items.split(",") if part.strip()]
        raw_items = indices
    elif raw_items is None:
        raw_items = []

    sender_inventory = inventory_items(sender)
    items: list[Entity] = []
    for raw_item in raw_items:
        if isinstance(raw_item, Entity):
            items.append(raw_item)
            continue
        try:
            item_idx = int(raw_item)
        except (TypeError, ValueError):
            item_idx = None
        if item_idx is not None and 0 <= item_idx < len(sender_inventory):
            items.append(sender_inventory[item_idx])
            continue
        matching_item = next((item for item in sender_inventory if item.name == str(raw_item)), None)
        if matching_item is not None:
            items.append(matching_item)

    try:
        currency = float(payload.get("currency", 0) or 0)
    except (TypeError, ValueError):
        currency = 0

    return Trade_Offer(items=items, currency=max(0, currency), request_text=str(payload.get("request", "")))


def _trade_round_info(
    speaker: Entity,
    recipients: list[Entity],
    current_offers: dict[Entity, dict[Entity, Trade_Offer]],
    round_idx: int,
    trade_duration: int,
) -> str:
    standing = []
    for recipient in recipients:
        offer = current_offers.get(speaker, {}).get(recipient)
        standing.append(f"to {recipient.name}: {_trade_offer_text(offer)}")

    incoming = []
    for other in recipients:
        offer = current_offers.get(other, {}).get(speaker)
        incoming.append(f"from {other.name}: {_trade_offer_text(offer)}")

    return (
        f"Trade round {round_idx + 1}/{trade_duration}. "
        f"Your current standing offer: {'; '.join(standing) or 'nothing'}. "
        f"Current offers to you: {'; '.join(incoming) or 'nothing'}. "
        "Make a revised proposal this round: add an item, remove an item, swap an item, or change currency. "
        "Only leave it empty if repeating your current standing offer is truly the best move."
    )


def _trade_message_info(
    speaker: Entity,
    recipients: list[Entity],
    current_offers: dict[Entity, dict[Entity, Trade_Offer]],
) -> str:
    outgoing = []
    for recipient in recipients:
        offer = current_offers.get(speaker, {}).get(recipient)
        outgoing.append(f"to {recipient.name}: {_trade_offer_text(offer)}")

    incoming = []
    for other in recipients:
        offer = current_offers.get(other, {}).get(speaker)
        incoming.append(f"from {other.name}: {_trade_offer_text(offer)}")

    return (
        "This is a trade negotiation. "
        f"Your offer: {'; '.join(outgoing) or 'nothing'}. "
        f"Offers to you: {'; '.join(incoming) or 'nothing'}. "
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
    ) -> Trade_Offer | dict[str, Trade_Offer] | dict[str, Any]:
        pass

    @abstractmethod
    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        pass

    @abstractmethod
    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass


def _trading_policy(entity: Entity) -> Trading_Policy | None:
    return entity.get_component(Trading_Policy)


def in_trade(entity: Entity) -> bool:
    policy = _trading_policy(entity)
    return bool(policy is not None and policy.in_trade)


def _transfer_offer(sender: Entity, recipient: Entity, offer: Trade_Offer, env: Environment) -> Trade_Offer:
    moved_items = []
    for item in offer.items:
        if not can_receive_trade_items(recipient):
            continue
        if _remove_item(sender, item) is None:
            continue
        if _add_item(recipient, item, env):
            moved_items.append(item)
        else:
            _add_item(sender, item, env)

    moved_currency = _move_currency(sender, recipient, offer.currency)
    return Trade_Offer(items=moved_items, currency=moved_currency, request_text=offer.request_text)


def _initial_offer_entities(
    participants: list[Entity],
    initial_offers: dict[str | Entity, dict[str | Entity, Trade_Offer | dict[str, Any]]] | None,
) -> dict[Entity, dict[Entity, Trade_Offer]]:
    by_name = {participant.name: participant for participant in participants}
    offers: dict[Entity, dict[Entity, Trade_Offer]] = {participant: {} for participant in participants}
    if not initial_offers:
        return offers

    for sender_key, recipient_offers in initial_offers.items():
        sender = sender_key if isinstance(sender_key, Entity) else by_name.get(str(sender_key))
        if sender is None:
            continue
        for recipient_key, payload in recipient_offers.items():
            recipient = recipient_key if isinstance(recipient_key, Entity) else by_name.get(str(recipient_key))
            if recipient is None or recipient is sender:
                continue
            offer = _offer_from_payload(payload, sender, recipient)
            if not _trade_offer_is_empty(offer):
                offers.setdefault(sender, {})[recipient] = offer

    return offers


def sim_simple_trade(
    participants: list[Entity],
    env: Environment,
    initial_offers: dict[str | Entity, dict[str | Entity, Trade_Offer | dict[str, Any]]] | None = None,
    trade_duration: int = 3,
) -> dict[str, Any]:
    policies = {participant: _trading_policy(participant) for participant in participants}
    if any(policy is None for policy in policies.values()):
        return {"error": "All trade participants need a Trading_Policy."}

    trade_info = f"Starting trade negotiation with {[participant.name for participant in participants]}."
    current_offers = _initial_offer_entities(participants, initial_offers)

    print(f"====== Starting trade with: {[participant.name for participant in participants]} ======")
    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            print(f"Initial offer from {sender.name} to {recipient.name}: {_trade_offer_text(offer)}")

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
            recipients = [participant for participant in participants if participant is not speaker]
            info = _trade_round_info(speaker, recipients, current_offers, round_idx, trade_duration)
            raw_offer = policy.send_trade_offer(recipients, env, info)

            for recipient in recipients:
                offer = _offer_from_payload(raw_offer, speaker, recipient)
                if _trade_offer_is_empty(offer):
                    continue
                current_offers.setdefault(speaker, {})[recipient] = offer
                print(f"Trade offer from {speaker.name} to {recipient.name}: {_trade_offer_text(offer)}")
                policies[recipient].receive_trade_offer(offer, speaker, env)

            message = policy.send_message(recipients, env, _trade_message_info(speaker, recipients, current_offers))
            print(f"{speaker.name}: {message}")
            for recipient in recipients:
                policies[recipient].receive_message(message, speaker, env)

    transfers = []
    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            moved = _transfer_offer(sender, recipient, offer, env)
            if moved.items or moved.currency > 0:
                transfers.append(
                    {
                        "from": sender.name,
                        "to": recipient.name,
                        "items": [item.name for item in moved.items],
                        "currency": moved.currency,
                    }
                )

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
