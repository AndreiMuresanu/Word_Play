from __future__ import annotations

from typing import Any

from word_play.core import Agent_Policy, Observation
from word_play.core.actions import Action_Selection
from word_play.presets.renderers.runtime import (
    prompt_human_action,
    prompt_human_action_kwargs,
)


class Human_Takes_Action(Agent_Policy):

    MAX_ATTEMPTS = 10

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict | None]:
        env = self._observation_env(observation)
        if self._renderer_for_env(env) is None:
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

    def _observation_env(self, observation: Observation) -> Any | None:
        if not observation.possible_actions:
            return None
        return observation.possible_actions[0].env

    def _renderer_for_env(self, env: Any | None) -> Any | None:
        return None if env is None else getattr(env, "renderer_impl", None)

    def _choose_action(self, observation: Observation) -> Action_Selection:
        env = self._observation_env(observation)
        renderer = self._renderer_for_env(env)
        if renderer is not None:
            return prompt_human_action(renderer, env, observation)
        if not observation.possible_actions:
            raise RuntimeError("No valid actions available for human-controlled entity.")

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
        renderer = self._renderer_for_env(action_selection.env)
        if renderer is not None:
            return prompt_human_action_kwargs(
                renderer,
                action_selection,
                max_attempts=self.MAX_ATTEMPTS,
            )

        for _ in range(self.MAX_ATTEMPTS):
            try:
                text = input(self._format_kwargs_prompt(action_selection))
                return action_selection.parse_and_validate_kwarg_list(text)
            except Exception:
                print("Invalid argument format. Try again.")

        raise RuntimeError("Too many invalid attempts entering arguments.")
