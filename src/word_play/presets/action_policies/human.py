from __future__ import annotations

from word_play.core import Agent_Policy, Observation
from word_play.core.actions import Action_Selection
from word_play.presets.human_io import Auto_Human_IO, Human_IO, Human_Text_Request


class Human_Takes_Action(Agent_Policy):

    MAX_ATTEMPTS = 10

    def __init__(self, io: Human_IO | None = None):
        super().__init__()
        self.io = io or Auto_Human_IO()

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict | None]:
        env = self._observation_env(observation)

        for retry_count in range(self.MAX_ATTEMPTS):
            action_selection = self._choose_action(observation, env=env)

            if action_selection.required_kwargs:
                kwargs = self._get_action_kwargs(action_selection)
                action_selection.action_kwargs = kwargs

            if action_selection.is_valid():
                break

            self.io.notify("Invalid action choice.", env=env)

            if retry_count >= self.MAX_ATTEMPTS - 1:
                raise RuntimeError("Too many invalid attempts selecting an action.")

        return action_selection, None

    def _observation_env(self, observation: Observation):
        if observation.possible_actions:
            return observation.possible_actions[0].env
        return None

    def _choose_action(self, observation: Observation, *, env=None) -> Action_Selection:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                idx_text = self.io.request_text(
                    self._action_selection_request(observation),
                    env=env,
                )
                idx = int(idx_text)
                if 0 <= idx < len(observation.possible_actions):
                    return observation.possible_actions[idx]

            except ValueError:
                pass
            self.io.notify("Invalid action index.", env=env)
        raise RuntimeError("Too many invalid attempts selecting an action.")

    def _action_selection_request(self, observation: Observation) -> Human_Text_Request:
        return Human_Text_Request(
            observation_text=str(observation),
        )

    def _format_kwargs_prompt(self, action_selection: Action_Selection) -> str:
        lines = ["Required arguments:"]

        for name, arg in action_selection.required_kwargs.items():
            desc = arg.arg_description(
                action_selection.actor,
                action_selection.target_entity,
                action_selection.env,
            )

            lines.append(f"  - {name}: {desc}")

        lines.append("")
        lines.append("Enter values separated by ';'")
        lines.append("Example: 'value1; value2; ...'")

        return "\n".join(lines)

    def _action_arguments_request(self, action_selection: Action_Selection) -> Human_Text_Request:
        return Human_Text_Request(
            observation_text=self._format_kwargs_prompt(action_selection),
        )

    def _get_action_kwargs(self, action_selection: Action_Selection) -> dict:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                text = self.io.request_text(
                    self._action_arguments_request(action_selection),
                    env=action_selection.env,
                )
                return action_selection.parse_and_validate_kwarg_list(text)

            except Exception:
                self.io.notify("Invalid argument format. Try again.", env=action_selection.env)
        raise RuntimeError("Too many invalid attempts entering arguments.")
