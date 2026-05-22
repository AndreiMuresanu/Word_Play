from __future__ import annotations

from abc import ABC, abstractmethod
import math
import re
import time
from types import MethodType
from typing import Any, TYPE_CHECKING

from word_play.core import Position
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.movement.single_point import Single_Point_Position
from word_play.presets.systems.communication.core import Communication_Policy
from word_play.presets.systems.communication.chat_room_action_communication.presets.policies import (
    Human_Communication_Policy,
)
from word_play.presets.systems.communication.trade_communication.core import Trade_Offer, Trading_Policy
from word_play.presets.systems.communication.trade_communication.trade_actions import Public_Trade_Offer
from word_play.presets.systems.containers import Container, Single_Item_Holder
from word_play.presets.systems.crafter import Crafter
from word_play.presets.systems.inventory import Inventory

from .renderer import Renderable
from .runtime import prompt_human_action, prompt_human_multi_select, prompt_human_text
from .wall_geometry import infer_enclosed_floor_positions

if TYPE_CHECKING:
    from word_play.core import Environment


def _is_in_any_inventory(item, env) -> bool:
    """Check if item is in any entity's inventory."""
    for entity in env.state.entities:
        inventory = entity.get_component(Inventory)
        if inventory and item in inventory.contents:
            return True
    return False


def _is_in_closed_container(item, env) -> bool:
    """Check if item is in a hidden/closed container."""
    for entity in env.state.entities:
        container = entity.get_component(Container)
        if container and item in container.contents:
            if container.visibility == "hidden" and not container.is_open:
                return True
    return False


def _component_named(entity, class_name: str):
    for component in getattr(entity, "components", {}).values():
        if component.__class__.__name__ == class_name:
            return component
    return None


def _inventory_items(entity) -> list:
    inventory = entity.get_component(Inventory) if hasattr(entity, "get_component") else None
    if inventory is None:
        return []
    return list(getattr(inventory, "contents", getattr(inventory, "inventory", [])))


def _money_amount(entity) -> float:
    for component in getattr(entity, "components", {}).values():
        if hasattr(component, "amount"):
            try:
                return float(component.amount)
            except (TypeError, ValueError):
                return 0
    return 0


def _parse_human_action_arg(action_selection, name: str, text: str):
    arg = action_selection.required_kwargs[name]
    return arg.parse_and_validate(
        text,
        action_selection.actor,
        action_selection.target_entity,
        action_selection.env,
    )


def _prompt_public_trade_action_kwargs(active_renderer, action_selection, error_message: str | None = None) -> dict:
    actor = action_selection.actor
    env = action_selection.env
    trade_items = _inventory_items(actor)
    currency_available = _money_amount(actor)
    base_instructions = [
        str(action_selection),
        "Build a public offer.",
        f"Currency available: {currency_available:g}",
        *( [f"Error: {error_message}"] if error_message else [] ),
    ]

    selected_text = prompt_human_multi_select(
        active_renderer,
        env,
        entity_name=actor.name,
        position_label=str(actor.position),
        header="Public Trade Items",
        instructions=[
            *base_instructions,
            "Select the items you want to give.",
            "Use Up/Down to move.",
            "Press Space to select or deselect the highlighted item.",
            "Press Enter to go to the next step.",
        ],
        options=[(idx, item.name) for idx, item in enumerate(trade_items)],
    )
    offer_items = _parse_human_action_arg(action_selection, "offer items", selected_text)

    currency_error = None
    while True:
        currency_text = prompt_human_text(
            active_renderer,
            env,
            entity_name=actor.name,
            position_label=str(actor.position),
            header="Public Trade Currency",
            instructions=[
                *base_instructions,
                "Type the currency amount you want to give, or leave blank for 0.",
                *( [f"Error: {currency_error}"] if currency_error else [] ),
            ],
            initial_text="0",
        )
        try:
            offer_currency = _parse_human_action_arg(action_selection, "offer currency", currency_text.strip() or "0")
            break
        except Exception as exc:
            currency_error = str(exc)

    request_text = prompt_human_text(
        active_renderer,
        env,
        entity_name=actor.name,
        position_label=str(actor.position),
        header="Public Trade Request",
        instructions=[
            *base_instructions,
            "Type what you want in return.",
            "Example: Berry, Cheese, or 1 gold.",
        ],
    )
    request = _parse_human_action_arg(action_selection, "request", request_text)
    return {
        "offer items": offer_items,
        "offer currency": offer_currency,
        "request": request,
    }


def _publish_render_speech_bubble(env, entity_name: str, message: str | None, ttl: int = 2) -> None:
    if message is None or not hasattr(env, "__dict__"):
        return
    text = str(message).strip()
    if not text:
        return

    existing = [
        bubble
        for bubble in list(getattr(env, "speech_bubbles", []))
        if not (
            isinstance(bubble, dict)
            and bubble.get("_kind") == "speech"
            and bubble.get("entity_name") == entity_name
        )
    ]
    existing.append({
        "entity_name": entity_name,
        "text": text,
        "_kind": "speech",
        "_step": getattr(env, "cur_step", 0),
        "ttl": ttl,
    })
    env.speech_bubbles = existing


def _publish_renderer_private_chat_window(env) -> None:
    if not hasattr(env, "__dict__"):
        return

    participant_names = list(getattr(env, "_renderer_conversation_participants", []))
    messages = [
        message
        for message in list(getattr(env, "_renderer_conversation_log", []))
        if ": " in str(message)
    ][-6:]
    if len(participant_names) < 2 or not messages:
        return

    existing = [
        bubble
        for bubble in list(getattr(env, "speech_bubbles", []))
        if not (isinstance(bubble, dict) and bubble.get("_kind") == "chat_session")
    ]
    existing.append(
        {
            "entity_name": participant_names[0],
            "participant_names": participant_names,
            "messages": messages,
            "_kind": "chat_session",
            "_step": getattr(env, "cur_step", 0),
            "ttl": 1,
        }
    )
    env.speech_bubbles = existing


def _clear_renderer_private_chat_windows(env) -> None:
    if not hasattr(env, "__dict__"):
        return
    env.speech_bubbles = [
        bubble
        for bubble in list(getattr(env, "speech_bubbles", []))
        if not (isinstance(bubble, dict) and bubble.get("_kind") == "chat_session")
    ]


def _render_conversation_update_from_renderer(env) -> None:
    renderer = getattr(env, "renderer_impl", None)
    if renderer is None or getattr(renderer, "_rendering_conversation_update", False):
        return

    renderer._rendering_conversation_update = True
    try:
        renderer.render(env)
        delay = float(getattr(env, "conversation_render_delay", 0.45))
        if delay > 0:
            time.sleep(delay)
    finally:
        renderer._rendering_conversation_update = False


def _looks_like_trade_conversation(info: str | None) -> bool:
    return bool(info and "trade negotiation" in str(info).lower())


def _nearby_communication_partner_names(actor, env) -> set[str]:
    movement_system = getattr(env, "movement_system", None)
    positions_are_close = getattr(movement_system, "positions_are_close", None)
    if not callable(positions_are_close):
        return set()

    return {
        entity.name
        for entity in getattr(getattr(env, "state", None), "entities", [])
        if (
            entity is not actor
            and hasattr(entity, "has_component")
            and entity.has_component(Communication_Policy)
            and positions_are_close(actor.position, entity.position)
        )
    }


def _infer_conversation_visibility(env, participants) -> str:
    if len(participants) < 2:
        return "public"

    starter = participants[-1]
    participant_names = {
        participant.name
        for participant in participants
        if participant is not starter and hasattr(participant, "name")
    }
    nearby_names = _nearby_communication_partner_names(starter, env)
    if nearby_names and nearby_names.issubset(participant_names):
        return "public"
    return "private"


def _trade_items_field(offer: Trade_Offer | None) -> str:
    if offer is None or not offer.items:
        return "none"
    return ",".join(item.name for item in offer.items)


def _trade_currency_field(offer: Trade_Offer | None) -> str:
    if offer is None or offer.currency <= 0:
        return ""
    return f"{offer.currency:g}"


def _trade_session_text(left, right, offers: dict[tuple[str, str], Trade_Offer], accepted: bool) -> str:
    left_offer = offers.get((left.name, right.name))
    right_offer = offers.get((right.name, left.name))
    accepted_text = "yes" if accepted else "no"
    return (
        "TRADE_SESSION:|"
        f"left:{left.name}|right:{right.name}|"
        f"left_offer:{_trade_items_field(left_offer)}|"
        f"left_currency:{_trade_currency_field(left_offer)}|"
        f"right_offer:{_trade_items_field(right_offer)}|"
        f"right_currency:{_trade_currency_field(right_offer)}|"
        f"accepted:{accepted_text}"
    )


def _trade_window_messages(env, participant_names: set[str], limit: int = 2) -> list[str]:
    messages = []
    for entry in list(getattr(env, "_renderer_conversation_log", [])):
        text = str(entry).strip()
        if ": " not in text:
            continue
        speaker_text = text.split(" - ", 1)[1] if text.startswith("Round ") and " - " in text else text
        speaker_name = speaker_text.split(":", 1)[0].strip()
        if speaker_name in participant_names:
            messages.append(speaker_text)
    return messages[-limit:]


def _publish_renderer_trade_windows(env, accepted: bool = False) -> None:
    if not hasattr(env, "__dict__"):
        return

    participant_names = list(getattr(env, "_renderer_conversation_participants", []))
    if len(participant_names) < 2:
        return

    entity_by_name = {
        entity.name: entity
        for entity in getattr(getattr(env, "state", None), "entities", [])
        if hasattr(entity, "name")
    }
    participants = [entity_by_name[name] for name in participant_names if name in entity_by_name]
    if len(participants) < 2:
        return

    offers = dict(getattr(env, "_renderer_trade_offers", {}))
    existing = [
        bubble
        for bubble in list(getattr(env, "speech_bubbles", []))
        if not (isinstance(bubble, dict) and bubble.get("_kind") == "trade_session")
    ]

    for left_idx, left in enumerate(participants):
        for right in participants[left_idx + 1 :]:
            participant_pair = {left.name, right.name}
            existing.append(
                {
                    "entity_name": left.name,
                    "partner_name": right.name,
                    "text": _trade_session_text(left, right, offers, accepted),
                    "messages": _trade_window_messages(env, participant_pair),
                    "_kind": "trade_session",
                    "_step": getattr(env, "cur_step", 0),
                    "ttl": 1,
                }
            )

    env.speech_bubbles = existing


def _clear_renderer_trade_windows(env) -> None:
    if not hasattr(env, "__dict__"):
        return
    env.speech_bubbles = [
        bubble
        for bubble in list(getattr(env, "speech_bubbles", []))
        if not (isinstance(bubble, dict) and bubble.get("_kind") == "trade_session")
    ]


def _render_trade_update_from_renderer(env) -> None:
    renderer = getattr(env, "renderer_impl", None)
    if renderer is None or getattr(renderer, "_rendering_trade_update", False):
        return

    renderer._rendering_trade_update = True
    try:
        renderer.render(env)
        delay = float(getattr(env, "trade_render_delay", 0.45))
        if delay > 0:
            time.sleep(delay)
    finally:
        renderer._rendering_trade_update = False


def _install_trade_render_hooks(env) -> None:
    """Publish and redraw trade windows from renderer-side trade hooks."""
    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue
        renderable = entity.get_component(Renderable)
        public_offer = entity.get_component(Public_Trade_Offer)
        if renderable is not None and public_offer is not None and not getattr(public_offer, "_renderer_public_offer_hook_installed", False):
            original_post_offer = public_offer.post_offer
            original_refund = public_offer.refund

            def wrapped_post_offer(self, offer, env=None, *, _original=original_post_offer):
                self._renderer_public_offer_posting = True
                try:
                    return _original(offer, env)
                finally:
                    self._renderer_public_offer_posting = False
                    if env is not None:
                        _render_trade_update_from_renderer(env)

            def wrapped_refund(self, env=None, *, _original=original_refund):
                result = _original(env)
                if env is not None and not getattr(self, "_renderer_public_offer_posting", False):
                    _render_trade_update_from_renderer(env)
                return result

            public_offer.post_offer = MethodType(wrapped_post_offer, public_offer)
            public_offer.refund = MethodType(wrapped_refund, public_offer)
            public_offer._renderer_public_offer_hook_installed = True

        policy = entity.get_component(Trading_Policy)
        if renderable is None or policy is None:
            continue
        if getattr(policy, "_renderer_trade_hook_installed", False):
            continue

        original_receive_trade_offer = policy.receive_trade_offer
        original_end_trade = policy.end_trade

        def wrapped_receive_trade_offer(self, offer, sender, env, *, _original=original_receive_trade_offer):
            result = _original(offer, sender, env)
            recipient = getattr(self, "entity", None)
            if recipient is not None and hasattr(env, "__dict__"):
                offers = dict(getattr(env, "_renderer_trade_offers", {}))
                offers[(sender.name, recipient.name)] = offer
                env._renderer_trade_offers = offers
                env._renderer_trade_end_rendered = False
                _publish_renderer_trade_windows(env)
                _render_trade_update_from_renderer(env)
            return result

        def wrapped_end_trade(self, participants, env, info=None, *, _original=original_end_trade):
            result = _original(participants, env, info)
            if not getattr(env, "_renderer_trade_end_rendered", False):
                _publish_renderer_trade_windows(env, accepted=True)
                _render_trade_update_from_renderer(env)
                _clear_renderer_trade_windows(env)
                env._renderer_trade_end_rendered = True
            return result

        policy.receive_trade_offer = MethodType(wrapped_receive_trade_offer, policy)
        policy.end_trade = MethodType(wrapped_end_trade, policy)
        policy._renderer_trade_hook_installed = True


def _install_communication_render_hooks(env) -> None:
    """Publish chat messages into renderer-owned speech bubbles."""
    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue
        renderable = entity.get_component(Renderable)
        policy = entity.get_component(Communication_Policy)
        if renderable is None or policy is None:
            continue
        if getattr(policy, "_renderer_message_hook_installed", False):
            continue

        original_start = policy.start_conversation
        original_send = policy.send_message
        original_end = policy.end_conversation

        def wrapped_start(self, participants, env, info=None, *, _original=original_start):
            depth = int(getattr(env, "_renderer_conversation_depth", 0))
            if depth == 0:
                conversation_kind = "trade" if _looks_like_trade_conversation(info) else "chat"
                conversation_visibility = _infer_conversation_visibility(env, participants)
                env._renderer_conversation_log = []
                env._renderer_conversation_participants = [participant.name for participant in participants]
                starter_name = getattr(getattr(self, "entity", None), "name", "Unknown")
                env._renderer_conversation_starter = starter_name
                env._renderer_conversation_kind = conversation_kind
                env._renderer_conversation_visibility = conversation_visibility
                if conversation_kind == "trade":
                    env._renderer_trade_offers = {}
                    env._renderer_trade_end_rendered = False
                    env._renderer_conversation_log.append(f"Trade started by {starter_name}")
                elif conversation_visibility == "private":
                    env._renderer_conversation_log.append(f"Private chat started by {starter_name}")
                else:
                    env._renderer_conversation_log.append(f"Conversation started by {starter_name}")
            env._renderer_conversation_depth = depth + 1
            return _original(participants, env, info)

        def wrapped_send(self, recipients, env, info=None, *, _original=original_send):
            conversation_kind = getattr(env, "_renderer_conversation_kind", "chat")
            speaker_name = getattr(getattr(self, "entity", None), "name", "Unknown")

            message = _original(recipients, env, info)
            if message is not None and str(message).strip():
                conversation_log = list(getattr(env, "_renderer_conversation_log", []))
                participant_count = max(1, len(getattr(env, "_renderer_conversation_participants", [])))
                prior_messages = max(
                    0,
                    len([entry for entry in conversation_log if entry.startswith("Round ") and ": " in entry])
                )
                round_number = prior_messages // participant_count + 1
                entry = f"Round {round_number} - {speaker_name}: {message}"
                conversation_log.append(entry)
                env._renderer_conversation_log = conversation_log[-8:]
                if conversation_kind != "trade":
                    if getattr(env, "_renderer_conversation_visibility", "public") == "private":
                        _publish_renderer_private_chat_window(env)
                    else:
                        _publish_render_speech_bubble(env, speaker_name, str(message))
                    _render_conversation_update_from_renderer(env)
            return message

        def wrapped_end(self, participants, env, info=None, *, _original=original_end):
            try:
                return _original(participants, env, info)
            finally:
                depth = max(0, int(getattr(env, "_renderer_conversation_depth", 0)) - 1)
                env._renderer_conversation_depth = depth
                if depth == 0:
                    if getattr(env, "_renderer_conversation_visibility", "public") == "private":
                        _clear_renderer_private_chat_windows(env)
                    env._renderer_conversation_participants = []
                    env._renderer_conversation_log = []
                    env._renderer_conversation_starter = None
                    env._renderer_conversation_kind = None
                    env._renderer_conversation_visibility = None
                    env._renderer_trade_offers = {}
                    env._renderer_trade_end_rendered = False

        policy.start_conversation = MethodType(wrapped_start, policy)
        policy.send_message = MethodType(wrapped_send, policy)
        policy.end_conversation = MethodType(wrapped_end, policy)
        policy._renderer_message_hook_installed = True


def _expire_render_messages(env) -> None:
    """Clear legacy Renderable.last_message values after they have been visible briefly."""
    current_step = getattr(env, "cur_step", 0)
    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue
        renderable = entity.get_component(Renderable)
        if renderable is None:
            continue
        message_step = getattr(renderable, "_last_message_step", None)
        if message_step is None:
            continue
        if current_step > message_step + 1:
            renderable.last_message = None
            renderable._last_message_step = None


def _install_human_prompt_hooks(env) -> None:
    """Patch human action/chat components at runtime when a renderer is active."""
    renderer = getattr(env, "renderer_impl", None)
    if renderer is None:
        return

    for entity in getattr(getattr(env, "state", None), "entities", []):
        if not hasattr(entity, "get_component"):
            continue

        if Human_Takes_Action is not None:
            action_policy = entity.get_component(Human_Takes_Action)
            if action_policy is not None and not getattr(action_policy, "_renderer_prompt_hook_installed", False):
                original_choose = action_policy._choose_action
                original_kwargs = action_policy._get_action_kwargs

                def wrapped_choose(self, observation, *, _original=original_choose):
                    active_renderer = getattr(observation.possible_actions[0].env, "renderer_impl", None) if observation.possible_actions else None
                    if active_renderer is None:
                        return _original(observation)
                    return prompt_human_action(active_renderer, observation.possible_actions[0].env, observation)

                def wrapped_kwargs(self, action_selection, *, _original=original_kwargs):
                    active_renderer = getattr(action_selection.env, "renderer_impl", None)
                    if active_renderer is None:
                        return _original(action_selection)
                    error_message = None
                    while True:
                        if action_selection.action.__class__.__name__ == "Start_Public_Trade":
                            try:
                                return _prompt_public_trade_action_kwargs(
                                    active_renderer,
                                    action_selection,
                                    error_message=error_message,
                                )
                            except Exception as exc:
                                error_message = str(exc)
                                continue

                        if (
                            action_selection.required_kwargs
                            and len(action_selection.required_kwargs) == 1
                        ):
                            arg_name, arg = next(iter(action_selection.required_kwargs.items()))
                            arg_description = arg.arg_description(
                                action_selection.actor,
                                action_selection.target_entity,
                                action_selection.env,
                            )
                            matches = re.findall(r"(\d+)\s*\(([^)]+)\)", arg_description)
                            if matches:
                                text = prompt_human_multi_select(
                                    active_renderer,
                                    action_selection.env,
                                    entity_name=action_selection.actor.name,
                                    position_label=str(action_selection.actor.position),
                                    header="Action Arguments",
                                    instructions=[
                                        str(action_selection),
                                        f"Choose values for: {arg_name}",
                                        "Use Up/Down to move.",
                                        "Press Space to select or deselect the highlighted item.",
                                        "Press Enter to go to the next step.",
                                        *( [f"Error: {error_message}"] if error_message else [] ),
                                    ],
                                    options=[(int(idx), label) for idx, label in matches],
                                )
                                try:
                                    return action_selection.parse_and_validate_kwarg_list(text)
                                except Exception as exc:
                                    error_message = str(exc)
                                    continue

                        instructions = [
                            str(action_selection),
                            "Type the required values separated by ';'.",
                            "Press Enter to go to the next step.",
                        ]
                        if action_selection.required_kwargs:
                            for name, arg in action_selection.required_kwargs.items():
                                instructions.append(
                                    f'{name}: {arg.arg_description(action_selection.actor, action_selection.target_entity, action_selection.env)}'
                                )
                        if error_message:
                            instructions.append(f"Error: {error_message}")

                        text = prompt_human_text(
                            active_renderer,
                            action_selection.env,
                            entity_name=action_selection.actor.name,
                            position_label=str(action_selection.actor.position),
                            header="Action Arguments",
                            instructions=instructions,
                        )
                        try:
                            return action_selection.parse_and_validate_kwarg_list(text)
                        except Exception as exc:
                            error_message = str(exc)

                action_policy._choose_action = MethodType(wrapped_choose, action_policy)
                action_policy._get_action_kwargs = MethodType(wrapped_kwargs, action_policy)
                action_policy._renderer_prompt_hook_installed = True

        if Human_Communication_Policy is not None:
            comm_policy = entity.get_component(Human_Communication_Policy)
            if comm_policy is not None and not getattr(comm_policy, "_renderer_prompt_hook_installed", False):
                original_send = comm_policy.send_message

                def wrapped_send(self, recipients, env, info=None, *, _original=original_send):
                    active_renderer = getattr(env, "renderer_impl", None)
                    if active_renderer is None or self.entity is None:
                        return _original(recipients, env, info)
                    is_trade = (
                        getattr(env, "_renderer_conversation_kind", "chat") == "trade"
                        or _looks_like_trade_conversation(info)
                    )
                    recipient_names = ", ".join(recipient.name for recipient in recipients) or "nobody"
                    transcript = list(getattr(env, "_renderer_conversation_log", []))
                    instructions = [
                        f"Recipients: {recipient_names}",
                        *([str(info)] if info else []),
                    ]
                    if transcript:
                        instructions.append("Negotiation so far:" if is_trade else "Conversation so far:")
                        instructions.extend(transcript[-6:])
                    instructions.extend([
                        f"Now {'negotiating' if is_trade else 'speaking'}: {self.entity.name}",
                        f"Type your {'negotiation' if is_trade else 'chat'} message.",
                        "Press Enter to send.",
                    ])
                    return prompt_human_text(
                        active_renderer,
                        env,
                        entity_name=self.entity.name,
                        position_label=str(self.entity.position),
                        header="Trade Negotiation" if is_trade else "Chat",
                        instructions=instructions,
                    )

                comm_policy.send_message = MethodType(wrapped_send, comm_policy)
                comm_policy._renderer_prompt_hook_installed = True

        trade_policy = _component_named(entity, "Human_Trading_Policy")
        if trade_policy is not None:
            if not getattr(trade_policy, "_renderer_trade_offer_prompt_hook_installed", False):
                original_send = trade_policy.send_trade_offer

                def wrapped_trade_offer(self, recipients, env, info=None, *, _original=original_send):
                    active_renderer = getattr(env, "renderer_impl", None)
                    if active_renderer is None or self.entity is None:
                        return _original(recipients, env, info)

                    def prompt_offer(recipient=None):
                        trade_items = _inventory_items(self.entity)
                        recipient_text = f" for {recipient.name}" if recipient is not None else ""
                        currency_available = _money_amount(self.entity)
                        base_instructions = [
                            f"Build trade offer{recipient_text}.",
                            *([str(info)] if info else []),
                            f"Currency available: {currency_available:g}",
                        ]
                        selected_text = prompt_human_multi_select(
                            active_renderer,
                            env,
                            entity_name=self.entity.name,
                            position_label=str(self.entity.position),
                            header="Trade Items",
                            instructions=[
                                *base_instructions,
                                "Use Up/Down to move.",
                                "Press Space to select or deselect the highlighted item.",
                                "Press Enter to go to the next step.",
                            ],
                            options=[(idx, item.name) for idx, item in enumerate(trade_items)],
                        )
                        item_indices = self._parse_item_indices(selected_text, len(trade_items))

                        error_message = None
                        for _ in range(self.MAX_ATTEMPTS):
                            currency_text = prompt_human_text(
                                active_renderer,
                                env,
                                entity_name=self.entity.name,
                                position_label=str(self.entity.position),
                                header="Trade Currency",
                                instructions=[
                                    *base_instructions,
                                    "Type a currency amount, or leave blank for 0.",
                                    *( [f"Error: {error_message}"] if error_message else [] ),
                                ],
                                initial_text="0",
                            )
                            try:
                                currency = self._parse_currency(currency_text, currency_available)
                                return {
                                    "items": [trade_items[idx] for idx in item_indices],
                                    "currency": currency,
                                }
                            except ValueError as exc:
                                error_message = str(exc)

                        raise RuntimeError("Too many invalid trade-offer attempts.")

                    if len(recipients) <= 1:
                        return prompt_offer(recipients[0] if recipients else None)
                    return {recipient.name: prompt_offer(recipient) for recipient in recipients}

                trade_policy.send_trade_offer = MethodType(wrapped_trade_offer, trade_policy)
                trade_policy._renderer_trade_offer_prompt_hook_installed = True


class Position_Layout_Adapter(ABC):
    """Map environment positions and optional backgrounds into render space."""
    @abstractmethod
    def screen_position(self, position: Position) -> tuple[float, float]:
        """Convert a world position into renderer grid coordinates."""

    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return background tiles to draw behind entities."""
        return []

    def prepare_env(self, env: "Environment") -> None:
        """Update any renderer-facing derived state before drawing."""
        return None


class Grid_Layout_Adapter(Position_Layout_Adapter):
    """Use entity x/y values directly as grid coordinates."""
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Return empty - backgrounds are handled by renderer."""
        return []

    def screen_position(self, position: Position | Any) -> tuple[float, float]:
        """Project the position without changing its coordinates."""
        x = getattr(position, 'x', None)
        y = getattr(position, 'y', None)
        if x is not None and y is not None:
            return float(x), float(y)
        # Fallback for plain tuple positions: (x, y) or (x, y, z)
        if hasattr(position, '__getitem__') and len(position) >= 2:
            return float(position[0]), float(position[1])
        return 0.0, 0.0


def _get_slot_offsets(n: int, radius: float) -> list[tuple[float, float]]:
    """Return predefined visual offsets for n entities at a single point.

    Layouts:
    - 1 entity: center
    - 2 entities: left/right
    - 3 entities: triangle (top + bottom corners)
    - 4 entities: compass layout (N, E, S, W)
    - 5-8: evenly distributed ring
    - 9+: concentric rings
    """
    if n == 1:
        return [(0.0, 0.0)]
    elif n == 2:
        # Left and right
        d = radius
        return [(-d, 0.0), (d, 0.0)]
    elif n == 3:
        # Triangle pointing up
        r = radius
        return [
            (0.0, -r),                    # Top
            (r * 0.866, r * 0.5),       # Bottom-right
            (-r * 0.866, r * 0.5),      # Bottom-left
        ]
    elif n == 4:
        # Compass layout (N, E, S, W) - classic "sharing a tile" look
        r = radius
        return [
            (0.0, -r),    # North (top)
            (r, 0.0),     # East (right)
            (0.0, r),     # South (bottom)
            (-r, 0.0),    # West (left)
        ]
    elif n <= 8:
        # Ring layout - evenly spaced around circle
        offsets = []
        for i in range(n):
            # Start at top, go clockwise
            angle = -math.pi / 2 + (2 * math.pi * i / n)
            offsets.append((
                radius * math.cos(angle),
                radius * math.sin(angle) * 0.7,  # Flatten Y for perspective
            ))
        return offsets
    else:
        # Concentric rings for large groups
        offsets = []
        ring_size = 8  # entities per outer ring
        for i in range(n):
            ring = i // ring_size
            index_in_ring = i % ring_size

            # Inner entities are closer, outer are further
            r = radius * (1 + ring * 0.5)
            angle = -math.pi / 2 + (2 * math.pi * index_in_ring / ring_size)
            offsets.append((
                r * math.cos(angle),
                r * math.sin(angle) * 0.7,
            ))
        return offsets


class SinglePointLayout(Position_Layout_Adapter):
    """Unified layout for entities at a single point position.

    Entities can be arranged in:
    - "compass" mode: N/E/S/W for up to 4, expanding to rings for more
    - "circle" mode: Circular arrangement with configurable radius

    Optional room background can be generated when include_room=True.
    """

    # Room background settings
    WALL_SET = "src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall"
    TABLE_SPRITE = "src/world_tiles/indoors/stations/prep_table.png"
    DEFAULT_FLOOR = "src/world_tiles/indoors/floors/white_grid_floor.png"

    def __init__(
        self,
        center_x: float = 0,
        center_y: float = 0,
        radius: float = 0.35,
        layout_mode: str = "compass",  # "compass" or "circle"
        include_room: bool = False,
        only_agents: bool = False,
    ):
        """
        Args:
            center_x, center_y: The grid coordinates of the center point
            radius: Base radius for positioning in tile units
            layout_mode: "compass" (N/E/S/W slots) or "circle" (pure circular)
            include_room: If True, generate room walls and floor tiles
            only_agents: If True, only position agents (ignore non-agent entities)
        """
        self.base_x = center_x
        self.base_y = center_y
        self.radius = radius
        self.base_radius = radius
        self.layout_mode = layout_mode
        self.include_room = include_room
        self.only_agents = only_agents
        self._cached_background: list[dict[str, Any]] | None = None
        self.room_width = 5
        self.room_height = 5

    def _calculate_room_size(self, n_agents: int) -> tuple[int, int]:
        """Calculate room size based on agent count."""
        if n_agents <= 4:
            return 5, 5
        elif n_agents <= 8:
            return 7, 7
        elif n_agents <= 12:
            return 9, 7
        else:
            return 11, 9

    @staticmethod
    def _get_floor_sprite() -> str:
        """Get a nice floor sprite."""
        return SinglePointLayout.DEFAULT_FLOOR

    def prepare_env(self, env: "Environment") -> None:
        """Calculate visual positions for entities at this point."""
        if env is None:
            return

        entities = list(getattr(env.state, "entities", []))

        # Filter entities to position
        if self.only_agents:
            positioned_entities = [e for e in entities if getattr(e, "is_agent", False)]
        else:
            positioned_entities = [
                e for e in entities
                if isinstance(getattr(e, "position", None), Single_Point_Position)
            ]

        n = len(positioned_entities)
        if n == 0:
            return

        # Sort for stable ordering: agents first, then by name
        positioned_entities.sort(key=lambda e: (
            0 if getattr(e, "is_agent", False) else 1,
            e.name,
        ))

        # Calculate room size if needed
        agent_count = len([e for e in positioned_entities if getattr(e, "is_agent", False)])
        if self.include_room and agent_count > 0:
            self.room_width, self.room_height = self._calculate_room_size(agent_count)
            self._cached_background = None

        # Calculate offsets based on layout mode
        if self.layout_mode == "compass":
            offsets = _get_slot_offsets(n, self.radius)
        else:  # circle
            offsets = []
            for i in range(n):
                angle = -math.pi / 2 + (2 * math.pi * i / n)
                offsets.append((
                    self.base_radius * math.cos(angle),
                    self.base_radius * math.sin(angle) * 0.7,
                ))

        # Assign offsets to each entity
        for entity, (offset_x, offset_y) in zip(positioned_entities, offsets):
            pos = entity.position
            if isinstance(pos, Single_Point_Position):
                pos.visual_offset_x = offset_x
                pos.visual_offset_y = offset_y

    def background(self, env: "Environment" | None) -> list[dict[str, Any]]:
        """Generate optional room background with walls and flooring."""
        if not self.include_room:
            return []

        if self._cached_background is not None:
            return self._cached_background

        if env is None:
            return []

        entities = list(getattr(env.state, "entities", []))
        agent_count = len([e for e in entities if getattr(e, "is_agent", False)])
        if agent_count == 0:
            return []

        room_w, room_h = self._calculate_room_size(agent_count)
        tiles = []

        half_w = room_w // 2
        half_h = room_h // 2

        # Generate interior floor tiles
        for y in range(-half_h, half_h + 1):
            for x in range(-half_w, half_w + 1):
                abs_x = self.base_x + x
                abs_y = self.base_y + y

                if x == 0 and y == 0:
                    # Meeting table at center
                    tiles.append({
                        "x": abs_x,
                        "y": abs_y,
                        "kind": "floor",
                        "sprite": self.TABLE_SPRITE,
                    })
                else:
                    tiles.append({
                        "x": abs_x,
                        "y": abs_y,
                        "kind": "floor",
                        "sprite": self._get_floor_sprite(),
                    })

        # Generate walls OUTSIDE the room
        wall_w = half_w + 1
        wall_h = half_h + 1

        for y in range(-wall_h, wall_h + 1):
            for x in range(-wall_w, wall_w + 1):
                is_outer_ring = (y == -wall_h or y == wall_h or x == -wall_w or x == wall_w)
                if not is_outer_ring:
                    continue

                abs_x = self.base_x + x
                abs_y = self.base_y + y

                tiles.append({
                    "x": abs_x,
                    "y": abs_y,
                    "kind": "wall",
                    "wall_set": self.WALL_SET,
                })

        self._cached_background = tiles
        return tiles

    def screen_position(self, position: Position | Any) -> tuple[float, float]:
        """Convert position to screen coordinates."""
        if isinstance(position, Single_Point_Position):
            offset_x = getattr(position, "visual_offset_x", 0.0)
            offset_y = getattr(position, "visual_offset_y", 0.0)
            return (self.base_x + offset_x, self.base_y + offset_y)

        # Fallback: try to get x/y attributes, default to center
        if position is not None:
            x = getattr(position, "x", None)
            y = getattr(position, "y", None)
            if x is not None and y is not None:
                return (float(x), float(y))

        return (self.base_x, self.base_y)


# Backward-compatible alias (deprecated, use SinglePointLayout)
Circle_Layout_Adapter = SinglePointLayout


_DEFAULT_FLOOR = "src/world_tiles/indoors/floors/white_grid_floor.png"


class Environment_Layout_Adapter(Grid_Layout_Adapter):
    """Grid layout that fetches background tiles from env or renderer."""
    def background(self, env: "Environment") -> list[dict[str, Any]]:
        """Fetch background tiles from env.background_tiles, then renderer, or auto-generate floor."""
        env_tiles = getattr(env, "background_tiles", None)
        if env_tiles:
            return list(env_tiles)
        # Auto-generate floor from self.floor_sprite + width/height
        floor_sprite = getattr(env, "floor_sprite", None) or _DEFAULT_FLOOR
        w = getattr(env, "width", 0)
        h = getattr(env, "height", 0)
        if w > 0 and h > 0:
            return [{"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                    for x in range(w) for y in range(h)]
        wall_positions = {
            (int(entity.position.x), int(entity.position.y))
            for entity in getattr(getattr(env, "state", None), "entities", [])
            if getattr(entity, "position", None) is not None
            and "wall" in getattr(entity, "tags", [])
            and hasattr(entity.position, "x")
            and hasattr(entity.position, "y")
        }
        if wall_positions:
            occupied_positions = {
                (int(entity.position.x), int(entity.position.y))
                for entity in getattr(getattr(env, "state", None), "entities", [])
                if getattr(entity, "position", None) is not None
                and hasattr(entity.position, "x")
                and hasattr(entity.position, "y")
            }
            inferred_tiles = [
                {"x": x, "y": y, "kind": "floor", "sprite": floor_sprite}
                for x, y in sorted(infer_enclosed_floor_positions(wall_positions, occupied_positions))
            ]
            if inferred_tiles:
                return inferred_tiles
        renderer = getattr(env, "renderer_impl", None)
        if renderer is not None and hasattr(renderer, "background_tiles"):
            return renderer.background_tiles()
        return []

    def prepare_env(self, env: "Environment") -> None:
        """Apply common renderer-side sync for inventories, holders, crafters, and containers."""
        _install_human_prompt_hooks(env)
        _install_communication_render_hooks(env)
        _install_trade_render_hooks(env)
        _expire_render_messages(env)

        for entity in getattr(getattr(env, "state", None), "entities", []):
            renderable = entity.get_component(Renderable) if hasattr(entity, "get_component") else None
            if renderable is None:
                continue

            inventory = entity.get_component(Inventory)
            holder = entity.get_component(Single_Item_Holder)
            crafter = entity.get_component(Crafter)
            container = entity.get_component(Container)

            if inventory is not None:
                held_item = inventory.contents[0] if inventory.contents else None
                held_renderable = None if held_item is None else held_item.get_component(Renderable)
                renderable.overlay_sprite = None if held_renderable is None else held_renderable.sprite_path
                renderable.overlay_mode = "badge"
                renderable.overlay_scale = 0.28
            elif holder is not None and holder.stored_item is not None:
                item_renderable = holder.stored_item.get_component(Renderable)
                if item_renderable is not None:
                    renderable.overlay_sprite = item_renderable.sprite_path
                    renderable.overlay_mode = "center"
                    renderable.overlay_scale = 0.75
            elif crafter is not None:
                if crafter.output_item is not None:
                    # Output is ready - show the crafted item
                    output_renderable = crafter.output_item.get_component(Renderable)
                    if output_renderable is not None:
                        renderable.overlay_sprite = output_renderable.sprite_path
                        renderable.overlay_mode = "center"
                        renderable.overlay_scale = 0.75
                elif crafter.active_recipe is not None and crafter.remaining_steps is not None:
                    # Crafting in progress - no overlay needed, just show in HUD
                    renderable.overlay_sprite = None
                else:
                    renderable.overlay_sprite = None
            else:
                renderable.overlay_sprite = None

            if "collectable" in entity.tags:
                renderable.visible = not _is_in_any_inventory(entity, env) and not _is_in_closed_container(entity, env)
