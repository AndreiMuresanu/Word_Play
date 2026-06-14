from __future__ import annotations

from word_play.core import Entity, Environment
from word_play.presets.human_io import Auto_Human_IO, Human_IO, Human_Text_Request
from word_play.presets.systems.communication.core import Communication_Policy


class Human_Communication_Policy(Communication_Policy):
    def __init__(self, io: Human_IO | None = None):
        super().__init__()
        self.io = io or Auto_Human_IO()

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        self.io.notify(f"====== Starting conversation with: {[entity.name for entity in participants]} ======", env=env)
        if info:
            self.io.notify(info, env=env)

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        body_lines = [f"Recipients: {', '.join(entity.name for entity in recipients) or 'nobody'}"]
        if info:
            body_lines.append(info)
        return self.io.request_text(
            Human_Text_Request(observation_text="\n".join(body_lines)),
            env=env,
        )

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        self.io.notify(f"Received message from {sender.name}: {message}", env=env)

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.io.notify(info, env=env)
        self.io.notify(f"====== Ending conversation with: {[entity.name for entity in participants]} ======", env=env)


class TalkingCow(Communication_Policy):
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        return "Moo."

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
