from __future__ import annotations

from word_play.core import Agent_Policy, Entity, Environment, Observation
from word_play.core.actions import Action_Selection
from word_play.presets.systems.communication.core import Communication_Policy


# TODO: this is just a template, this class needs to be implemented. This class should use some general LLM API so that
#       it can switch to use different LLMs very easily. It should not store the LLM in memory, since if we have many
#       agents, we don't want many copies of the same LLM. It should also manage its memory, e.g., it is responsible for
#       storing information about past observations and past chats with other agents.
#       This class should accept a Human_LLM class as input for its LLM (e.g., see model_presets.py). The Human_LLM
#       model sees the exact same thing as the LLM, the only difference is that the human is generating text instead of
#       the LLM. This is a very useful class for testing and debugging.
class LLM_Action_And_Communication_Policy(Agent_Policy, Communication_Policy):

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        pass

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        pass

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        pass

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        pass
