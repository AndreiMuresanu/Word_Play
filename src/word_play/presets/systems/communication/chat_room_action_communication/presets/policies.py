from __future__ import annotations

from word_play.core import Entity, Environment
from word_play.presets.human_io import Auto_Human_IO, Human_IO, Human_Text_Request
from word_play.presets.systems.communication.core import Communication_Policy


class Human_Communication_Policy(Communication_Policy):
    def __init__(self, io: Human_IO | None = None):
        super().__init__()
        self.io = io or Auto_Human_IO()
        self._active_participant_names: list[str] = []

    def _conversation_key(self, participants: list[Entity]) -> tuple[int, ...]:
        return tuple(sorted(id(entity) for entity in participants))

    def _active_conversation_keys(self, env: Environment) -> set[tuple[int, ...]]:
        keys = getattr(env, "_human_conversation_keys", None)
        if keys is None:
            keys = set()
            env._human_conversation_keys = keys
        return keys

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        participant_names = [entity.name for entity in participants]
        self._active_participant_names = participant_names
        key = self._conversation_key(participants)
        active_keys = self._active_conversation_keys(env)
        if key not in active_keys:
            active_keys.add(key)
            self.io.notify(f"Conversation started: {', '.join(participant_names)}", env=env)
        if info:
            self.io.notify(info, env=env)

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        speaker_name = self.entity.name if self.entity is not None else "Human"
        recipient_label = ", ".join(entity.name for entity in recipients) or "nobody"
        body_lines = [f"To: {recipient_label}"]
        if self._active_participant_names:
            body_lines.insert(0, f"Conversation: {', '.join(self._active_participant_names)}")
        if info:
            body_lines.append(info)
        return self.io.request_text(
            Human_Text_Request(
                observation_text="\n".join(body_lines),
                prompt=f"{speaker_name}> ",
            ),
            env=env,
        )

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        recipient_name = self.entity.name if self.entity is not None else "Human"
        self.io.notify(f"{sender.name} -> {recipient_name}: {message}", env=env)

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        participant_names = [entity.name for entity in participants]
        self._active_participant_names = []
        if info:
            self.io.notify(info, env=env)
        key = self._conversation_key(participants)
        active_keys = self._active_conversation_keys(env)
        if key in active_keys:
            active_keys.remove(key)
            self.io.notify(f"Conversation ended: {', '.join(participant_names)}", env=env)


class TalkingCow(Communication_Policy):
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        return "Moo."

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
