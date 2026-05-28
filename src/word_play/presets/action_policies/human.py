from __future__ import annotations

from word_play.core import Agent_Policy, Observation
from word_play.core.actions import Action_Selection


class Human_Takes_Action(Agent_Policy):

    MAX_ATTEMPTS = 10

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict | None]:
        print("--------------------")
        print(observation)

        for retry_count in range(self.MAX_ATTEMPTS):
            action_selection = self._choose_action(observation)

            if action_selection.required_kwargs:
                kwargs = self._get_action_kwargs(action_selection)
                action_selection.action_kwargs = kwargs

            if action_selection.is_valid():
                break

            print("Invalid action choice.")

            if retry_count >= self.MAX_ATTEMPTS - 1:
                raise RuntimeError("Too many invalid attempts selecting an action.")

        return action_selection, None

    def _choose_action(self, observation: Observation) -> Action_Selection:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                idx = int(input("Input action index: "))
                if 0 <= idx < len(observation.possible_actions):
                    return observation.possible_actions[idx]

            except ValueError:
                pass
            print("Invalid action index.")
        raise RuntimeError("Too many invalid attempts selecting an action.")

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

        return "\n".join(lines) + "\n> "

    def _get_action_kwargs(self, action_selection: Action_Selection) -> dict:
        for _ in range(self.MAX_ATTEMPTS):
            try:
                input_prompt = self._format_kwargs_prompt(action_selection)
                text = input(input_prompt)
                return action_selection.parse_and_validate_kwarg_list(text)

            except Exception:
                print("Invalid argument format. Try again.")
        raise RuntimeError("Too many invalid attempts entering arguments.")
