from __future__ import annotations

from word_play.core import Entity, Environment
from word_play.presets.systems.communication.core import Communication_Policy


class Human_Communication_Policy(Communication_Policy):

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        print(f"====== Starting conversation with: {[entity.name for entity in participants]} ======")
        if info:
            print(info)

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        if info:
            print(info)
        return input("Your message: ")

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        print(f"Received message from {sender.name}: {message}")

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            print(info)
        print(f"====== Ending conversation with: {[entity.name for entity in participants]} ======")


class TalkingCow(Communication_Policy):
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        return "Moo."

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
