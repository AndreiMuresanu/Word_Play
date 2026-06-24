from __future__ import annotations

from word_play.core import Entity, Environment
from word_play.presets.action_policies.llm_action_and_communication import (
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.human_io import Human_Text_Request
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import (
    Human_Communication_Policy,
)
from word_play.presets.systems.communication.trade_communication.core import (
    Offers_By_Recipient,
    Trade_Offer,
    Trading_Policy,
    offer_from_payload,
    resolve_item_indices,
    trade_offer_text,
)
from word_play.presets.systems.currency import Money, money_amount
from word_play.presets.systems.inventory import inventory_items


def _inventory_text(entity: Entity) -> str:
    items = inventory_items(entity)
    if not items:
        return "empty"
    return ", ".join(f"{idx}: {item.name}" for idx, item in enumerate(items))


class LLM_Trading_Policy(LLM_Action_And_Communication_Policy, Trading_Policy):
    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            self._trim_history()

    def send_trade_offer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> Offers_By_Recipient:
        parsed = self._request_offer_json(recipients, env, info)
        return {recipient: offer_from_payload(parsed, self.entity, recipient) for recipient in recipients}

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        self.conversation_history.append(
            {
                "role": "system",
                "content": f"Trade offer from {sender.name}: {trade_offer_text(offer)}.",
            }
        )
        self._trim_history()

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            self._trim_history()

    def _request_offer_json(self, recipients: list[Entity], env: Environment, info: str | None) -> dict:
        # Retry on malformed JSON like select_action; fall back to an empty (no-change) offer rather than aborting.
        prompt = self._trade_offer_prompt(recipients, env, info)
        for _ in range(self.MAX_ATTEMPTS):
            raw = self.model.generate_text(
                self._with_system(prompt),
                self.action_generation_config,
                max_new_tokens=self.action_max_new_tokens,
            ).strip()
            try:
                return self._extract_json(raw)
            except Exception as exc:
                prompt = self._retry_prompt(prompt, raw, str(exc))
        return {}

    def _trade_offer_prompt(self, recipients: list[Entity], env: Environment, info: str | None) -> str:
        recipient_names = ", ".join(entity.name for entity in recipients)
        recipient_blocks = []
        for recipient in recipients:
            recipient_blocks.append(
                f"{recipient.name}: inventory={_inventory_text(recipient)}; money={recipient.get_component(Money) or 'none'}"
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
            f"Your money: {self.entity.get_component(Money) or 'none'}\n"
            f"Recipients: {recipient_names}\n"
            f"Recipient state:\n{recipient_text}\n"
            f"{info_text}"
            f"Recent negotiation:\n{history}\n\n"
            "Reply with ONLY a JSON object in this format:\n"
            f"{output_format}\n\n"
            "Your JSON:"
        )


class Human_Trading_Policy(Human_Communication_Policy, Trading_Policy):
    def start_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.io.notify(info, env=env)

    def send_trade_offer(
        self, recipients: list[Entity], env: Environment, info: str | None = None
    ) -> Offers_By_Recipient:
        if info:
            self.io.notify(info, env=env)
        return {recipient: self._terminal_offer(recipient, env) for recipient in recipients}

    def receive_trade_offer(self, offer: Trade_Offer, sender: Entity, env: Environment) -> None:
        self.io.notify(f"Trade offer from {sender.name}: {trade_offer_text(offer)}", env=env)

    def end_trade(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.io.notify(info, env=env)

    def _terminal_offer(self, recipient: Entity, env: Environment) -> Trade_Offer:
        items = inventory_items(self.entity)
        item_text = self.io.request_text(
            Human_Text_Request(
                observation_text=f"Your inventory: {_inventory_text(self.entity)}",
                prompt=f"Item indices to offer to {recipient.name}, comma-separated or blank: ",
            ),
            env=env,
        )
        offered = resolve_item_indices([int(t) for t in item_text.split(",") if t.strip().isdigit()], items)

        available = money_amount(self.entity)
        currency_text = self.io.request_text(
            Human_Text_Request(observation_text="", prompt=f"Currency to offer (0 to {available:g}): "),
            env=env,
        ).strip()
        try:
            currency = min(max(0.0, float(currency_text or 0)), available)
        except ValueError:
            currency = 0.0
        return Trade_Offer(items=offered, currency=currency)
