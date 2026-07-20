from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from word_play.core import Entity, Environment
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems.currency import Money
from word_play.presets.systems.inventory import Inventory, inventory_has_room, inventory_items


@dataclass
class Trade_Offer:
    items: list[Entity] = field(default_factory=list)
    currency: float = 0
    request_text: str = ""


# A policy's per-round output: the offer it is making to each recipient.
Offers_By_Recipient = dict[Entity, Trade_Offer]


def resolve_item_indices(indices: list[int], items: list[Entity], *, on_invalid: str = "skip") -> list[Entity]:
    """Map indices to items, order-preserving and de-duplicated. on_invalid='raise' rejects bad indices."""
    resolved: list[Entity] = []
    for idx in indices:
        if 0 <= idx < len(items):
            if items[idx] not in resolved:
                resolved.append(items[idx])
        elif on_invalid == "raise":
            raise ValueError("Selected item index is outside your inventory.")
    return resolved


def _move_currency(sender: Entity, recipient: Entity, amount: float) -> float:
    if amount <= 0:
        return 0
    sender_money = sender.get_component(Money)
    recipient_money = recipient.get_component(Money)
    if sender_money is None or recipient_money is None:
        return 0
    return sender_money.transfer_to(recipient_money, amount)


def _trade_offer_is_empty(offer: Trade_Offer | None) -> bool:
    return offer is None or (not offer.items and offer.currency <= 0 and not offer.request_text.strip())


def trade_offer_text(offer: Trade_Offer | None) -> str:
    if offer is None or (not offer.items and offer.currency <= 0):
        return "nothing"
    parts = []
    if offer.items:
        parts.append(", ".join(item.name for item in offer.items))
    if offer.currency > 0:
        parts.append(f"{offer.currency:g} currency")
    return " and ".join(parts)


def offer_from_payload(payload: Any, sender: Entity, recipient: Entity | None = None) -> Trade_Offer:
    """Normalize a raw payload (dict or Trade_Offer) into a Trade_Offer; handles flat and per-recipient nested dicts."""
    if isinstance(payload, Trade_Offer):
        return payload
    if not isinstance(payload, dict):
        return Trade_Offer()
    if recipient is not None and recipient.name in payload and "items" not in payload:
        return offer_from_payload(payload[recipient.name], sender, recipient)

    raw_items = payload.get("items") or []
    if isinstance(raw_items, str):
        raw_items = [part.strip() for part in raw_items.split(",") if part.strip()]

    inventory = inventory_items(sender)
    items: list[Entity] = []
    for raw in raw_items:
        if isinstance(raw, Entity):
            item = raw
        else:
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                idx = None
            item = inventory[idx] if idx is not None and 0 <= idx < len(inventory) else (
                next((it for it in inventory if it.name == str(raw)), None)
            )
        if item is not None and item not in items:
            items.append(item)

    try:
        currency = float(payload.get("currency", 0) or 0)
    except (TypeError, ValueError):
        currency = 0
    return Trade_Offer(items=items, currency=max(0, currency), request_text=str(payload.get("request", "")))


def _offer_summary(speaker, recipients, current_offers) -> tuple[str, str]:
    outgoing = "; ".join(f"to {r.name}: {trade_offer_text(current_offers.get(speaker, {}).get(r))}" for r in recipients)
    incoming = "; ".join(f"from {r.name}: {trade_offer_text(current_offers.get(r, {}).get(speaker))}" for r in recipients)
    return outgoing or "nothing", incoming or "nothing"


def _trade_round_info(speaker, recipients, current_offers, round_idx, trade_duration) -> str:
    standing, incoming = _offer_summary(speaker, recipients, current_offers)
    return (
        f"Trade round {round_idx + 1}/{trade_duration}. "
        f"Your current standing offer: {standing}. Current offers to you: {incoming}. "
        "Make a revised proposal this round: add an item, remove an item, swap an item, or change currency. "
        "Only leave it empty if repeating your current standing offer is truly the best move."
    )


def _trade_message_info(speaker, recipients, current_offers) -> str:
    outgoing, incoming = _offer_summary(speaker, recipients, current_offers)
    return (
        f"This is a trade negotiation. Your offer: {outgoing}. Offers to you: {incoming}. "
        "Send one short message about the deal."
    )


class Trading_Policy(Communication_Policy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.in_trade = False

    @abstractmethod
    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None: ...

    @abstractmethod
    def send_trade_offer(self, recipients: list[Entity], env: Environment, info: str | None = None) -> Offers_By_Recipient: ...

    @abstractmethod
    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None: ...

    @abstractmethod
    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None: ...


def in_trade(entity: Entity) -> bool:
    policy = entity.get_component(Trading_Policy)
    return bool(policy is not None and policy.in_trade)


def _transfer_offer(sender: Entity, recipient: Entity, offer: Trade_Offer, env: Environment) -> Trade_Offer:
    sender_inventory = sender.get_component(Inventory)
    recipient_inventory = recipient.get_component(Inventory)

    moved_items = []
    if sender_inventory is not None and recipient_inventory is not None:
        for item in offer.items:
            if not inventory_has_room(recipient):
                continue
            if sender_inventory.remove(item) is None:
                continue
            if recipient_inventory.add(item, env):
                moved_items.append(item)
            else:
                sender_inventory.add(item, env)

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
            offer = offer_from_payload(payload, sender, recipient)
            if not _trade_offer_is_empty(offer):
                offers.setdefault(sender, {})[recipient] = offer
    return offers


def _settle_trades(current_offers: dict[Entity, dict[Entity, Trade_Offer]], env: Environment) -> list[dict[str, Any]]:
    transfers: list[dict[str, Any]] = []
    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            moved = _transfer_offer(sender, recipient, offer, env)
            if moved.items or moved.currency > 0:
                transfers.append(
                    {"from": sender.name, "to": recipient.name,
                     "items": [item.name for item in moved.items], "currency": moved.currency}
                )
    return transfers


def sim_simple_trade(
    participants: list[Entity],
    env: Environment,
    initial_offers: dict[str | Entity, dict[str | Entity, Trade_Offer | dict[str, Any]]] | None = None,
    trade_duration: int = 3,
) -> dict[str, Any]:
    policies = {participant: participant.get_component(Trading_Policy) for participant in participants}
    if any(policy is None for policy in policies.values()):
        raise ValueError("All trade participants need a Trading_Policy.")
    trade_duration = max(0, trade_duration)

    names = [participant.name for participant in participants]
    trade_info = f"Starting trade negotiation with {names}."
    current_offers = _initial_offer_entities(participants, initial_offers)

    print(f"====== Starting trade with: {names} ======")
    for sender, recipient_offers in current_offers.items():
        for recipient, offer in recipient_offers.items():
            print(f"Initial offer from {sender.name} to {recipient.name}: {trade_offer_text(offer)}")

    try:
        for policy in policies.values():
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
                recipients = [p for p in participants if p is not speaker]
                offers = policy.send_trade_offer(
                    recipients, env, _trade_round_info(speaker, recipients, current_offers, round_idx, trade_duration)
                )
                for recipient in recipients:
                    offer = offers.get(recipient)
                    if _trade_offer_is_empty(offer):
                        continue
                    current_offers.setdefault(speaker, {})[recipient] = offer
                    print(f"Trade offer from {speaker.name} to {recipient.name}: {trade_offer_text(offer)}")
                    policies[recipient].receive_trade_offer(offer, speaker, env)
                message = policy.send_message(recipients, env, _trade_message_info(speaker, recipients, current_offers))
                print(f"{speaker.name}: {message}")
                for recipient in recipients:
                    policies[recipient].receive_message(message, speaker, env)

        transfers = _settle_trades(current_offers, env)
        summary = {"transfers": transfers}
        print("------ Trade settlement ------")
        for transfer in transfers:
            items_text = ", ".join(transfer["items"]) or "no items"
            print(f"{transfer['from']} -> {transfer['to']}: {items_text} and {transfer['currency']:g} currency")
        if not transfers:
            print("No transfers.")

        for policy in policies.values():
            policy.end_trade(participants, env, str(summary))
            policy.end_conversation(participants, env, str(summary))
            policy.in_trade = False
        print(f"====== Ending trade with: {names} ======")
        return summary
    finally:
        # Guarantee no participant is left stuck mid-trade if a round/settlement raised.
        for policy in policies.values():
            if policy is not None and policy.in_trade:
                policy.end_conversation(participants, env, "")
                policy.in_trade = False
