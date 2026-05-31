from __future__ import annotations

from typing import Callable

from word_play.core import Action, Entity, Environment, Action_Validation, Target_Is_Self
from word_play.presets.action_args import Int_Arg, List_Arg
from word_play.presets.systems.communication.core import Communication_Policy


def nearby_conversation_partners(actor: Entity, env: Environment) -> list[Entity]:
    return [
        entity
        for entity in env.state.entities
        if (
            env.movement_system.positions_are_close(actor.position, entity.position)
            and entity is not actor
            and entity.has_component(Communication_Policy)
        )
    ]


# TODO: could add a turn order arg which takes as input an ordering func or a str keyword. Just need to be careful to
#       make sure that the same entity doesn't send a message twice in a row.
def sim_simple_conversation(participants: list[Entity], env: Environment, conversation_duration: int = 3) -> None:
    for speaker in participants:
        speaker.get_component(Communication_Policy).start_conversation(participants, env)

    for turn in range(conversation_duration):
        for speaker in participants:
            recipients = [entity for entity in participants if entity is not speaker]
            message = speaker.get_component(Communication_Policy).send_message(recipients, env)
            for recipient in recipients:
                recipient.get_component(Communication_Policy).receive_message(message, speaker, env)

    for speaker in participants:
        speaker.get_component(Communication_Policy).end_conversation(participants, env)


class A_Conversation_Partner_Is_Nearby(Action_Validation):
    def is_valid(self, actor: Entity, target_entity: Entity, env: Environment) -> bool:
        return len(nearby_conversation_partners(actor, env)) != 0


class Start_Public_Conversation(Action):

    def __init__(
        self,
        conversation_format: Callable[[list[Entity]], None] = sim_simple_conversation,
    ):
        self.conversation_format = conversation_format
        super().__init__(validation_rules=[Target_Is_Self(), A_Conversation_Partner_Is_Nearby()])

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        participants = nearby_conversation_partners(actor, env)
        participants.append(actor)
        self.conversation_format(participants, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return f"Start a conversation with everyone nearby: {[entity.name for entity in nearby_conversation_partners(actor, env)]}."


def partner_idx_list_is_valid(
    partner_indices: list[int], actor: Entity, target_entity: Entity, env: Environment
) -> bool:
    potential_partner_count = len(nearby_conversation_partners(actor, env))
    return all(0 <= idx < potential_partner_count for idx in partner_indices)


class Nearby_Partner_Indicies(List_Arg):

    def __init__(self):
        super().__init__(Int_Arg(), validators=[partner_idx_list_is_valid])

    def arg_description(self, actor, target_entity, env):
        potential_partners = nearby_conversation_partners(actor, env)
        partners_text = ", ".join(f"{idx} ({entity.name})" for idx, entity in enumerate(potential_partners))
        return f"list of indices representing the conversation participants: {partners_text}"


class Start_Private_Conversation(Action):

    def __init__(
        self,
        conversation_format: Callable[[list[Entity]], None] = sim_simple_conversation,
    ):
        self.conversation_format = conversation_format
        super().__init__(
            validation_rules=[Target_Is_Self(), A_Conversation_Partner_Is_Nearby()],
            required_kwargs={"conversation partners": Nearby_Partner_Indicies()},
        )

    def exec_action(self, actor: Entity, target_entity: Entity, env: Environment, kwargs: dict | None) -> dict | None:
        assert "conversation partners" in kwargs, "Action missing kwarg: 'conversation partners'"
        potential_participants = nearby_conversation_partners(actor, env)
        participants = [potential_participants[idx] for idx in kwargs["conversation partners"]]
        participants.append(actor)
        self.conversation_format(participants, env)

    def action_description_text(self, actor: Entity, target_entity: Entity, env: Environment) -> str:
        return "Start a private conversation with only some of the nearby people."
