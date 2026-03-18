from __future__ import annotations

from abc import ABC, abstractmethod

from word_play.core import Component, Entity, Environment


# TODO: not sure if the info args are required for end_conversation and send_message
class Communication_Policy(Component, ABC):
    @abstractmethod
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    @abstractmethod
    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        pass

    @abstractmethod
    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    @abstractmethod
    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
