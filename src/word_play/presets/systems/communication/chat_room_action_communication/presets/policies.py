from __future__ import annotations

from word_play.core import Entity, Environment
from word_play.presets.renderers.runtime import prompt_human_text
from word_play.presets.systems.communication.core import Communication_Policy


class Human_Communication_Policy(Communication_Policy):

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        print(f"====== Starting conversation with: {[entity.name for entity in participants]} ======")
        if info:
            print(info)

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        if getattr(env, "renderer_impl", None) is not None and self.entity is not None:
            return self._send_message_with_renderer(recipients, env, info)

        if info:
            print(info)
        return input("Your message: ")

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        print(f"Received message from {sender.name}: {message}")

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            print(info)
        print(f"====== Ending conversation with: {[entity.name for entity in participants]} ======")

    def _send_message_with_renderer(
        self,
        recipients: list[Entity],
        env: Environment,
        info: str | None = None,
    ) -> str:
        recipient_names = ", ".join(recipient.name for recipient in recipients) or "nobody"
        recent_messages = []
        for entity in getattr(getattr(env, "state", None), "entities", []):
            renderable = self._renderable_component(entity)
            if renderable is None or entity is self.entity:
                continue
            message = getattr(renderable, "last_chat_message", None) or getattr(renderable, "last_message", None)
            if message:
                recent_messages.append(f"{entity.name}: {message}")

        instructions = [
            f"Recipients: {recipient_names}",
            *([str(info)] if info else []),
        ]
        if recent_messages:
            instructions.append("Recent chat:")
            instructions.extend(recent_messages[-6:])
        instructions.extend([
            f"Now speaking: {self.entity.name}",
            "Type your message.",
            "Press Enter to send.",
        ])

        return prompt_human_text(
            env.renderer_impl,
            env,
            entity_name=self.entity.name,
            position_label=str(self.entity.position),
            header="Chat",
            instructions=instructions,
        )

    def _renderable_component(self, entity: Entity):
        for component in getattr(entity, "components", {}).values():
            if component.__class__.__name__ == "Renderable":
                return component
        return None


class TalkingCow(Communication_Policy):
    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        return "Moo."

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
