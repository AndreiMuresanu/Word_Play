from __future__ import annotations

import json
import re
from typing import Any

from word_play.core import Agent_Policy, Entity, Environment, Observation
from word_play.core.actions import Action_Selection
from word_play.presets.models import LLM_MODEL_REGISTRY, Model
from word_play.presets.observation.simple_observation import format_action_details
from word_play.presets.systems.communication.core import Communication_Policy


class LLM_Action_And_Communication_Policy(Agent_Policy, Communication_Policy):
    """
    A combined action-selection and communication policy backed by any Model.

    Action output format — JSON:
        {"action_choice_idx": <int>, "action_kwargs": {<key>: <value>, ...}}

    The policy does NOT store the model object itself — it holds only a string
    key into LLM_MODEL_REGISTRY. This means any number of agents can share one
    model without duplicating it in memory.

    Memory:
        - observation_history: rolling buffer of past observation strings,
          included as context in the selection prompt.
        - conversation_history: rolling buffer of dialogue turns.
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        model_key: str,
        system_prompt: str = "",
        action_generation_config: dict | None = None,
        message_generation_config: dict | None = None,
        reasoning_generation_config: dict | None = None,
        use_chain_of_thought: bool = False,
        conversation_memory_window: int = 12,
        observation_memory_window: int = 4,
        action_max_new_tokens: int = 96,
        message_max_new_tokens: int = 64,
        reasoning_max_new_tokens: int = 256,
        max_stored_observation_chars: int = 3000,
        max_stored_message_chars: int = 320,
    ):
        super().__init__()
        self.model_key = model_key
        self.system_prompt = system_prompt
        self.action_generation_config = action_generation_config
        self.message_generation_config = message_generation_config
        self.reasoning_generation_config = reasoning_generation_config
        self.use_chain_of_thought = use_chain_of_thought
        self.conversation_memory_window = conversation_memory_window
        self.observation_memory_window = observation_memory_window
        self.action_max_new_tokens = action_max_new_tokens
        self.message_max_new_tokens = message_max_new_tokens
        self.reasoning_max_new_tokens = reasoning_max_new_tokens
        self.max_stored_observation_chars = max_stored_observation_chars
        self.max_stored_message_chars = max_stored_message_chars

        self.observation_history: list[str] = []
        self.observation_summary: str | None = None
        self.conversation_history: list[dict[str, str]] = []

    @property
    def model(self) -> Model:
        return LLM_MODEL_REGISTRY.resolve(self.model_key)

    # -----------------------------------------------------------------------
    # Agent_Policy — action selection
    # -----------------------------------------------------------------------

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        reasoning: str | None = None

        if self.use_chain_of_thought:
            reasoning_prompt = self._reasoning_prompt(observation)
            reasoning = self.model.generate_text(
                self._with_system(reasoning_prompt),
                self.reasoning_generation_config,
                max_new_tokens=self.reasoning_max_new_tokens,
            ).strip()

        selection_prompt = self._selection_prompt(observation, reasoning)
        last_exc: Exception | None = None
        last_raw: str | None = None

        for attempt in range(self.MAX_ATTEMPTS):
            raw = self.model.generate_text(
                self._with_system(selection_prompt),
                self.action_generation_config,
                max_new_tokens=self.action_max_new_tokens,
            )
            last_raw = raw
            try:
                action_selection = self._parse_selection(raw, observation)
                action_choice_idx = self._action_choice_idx(action_selection, observation)
                self._record_observation(observation)
                info = {
                    "raw_response": raw,
                    "reasoning": reasoning,
                    "action_choice_idx": action_choice_idx,
                    "attempt": attempt + 1,
                }
                self._record_last_selection(action_selection, info)
                return action_selection, info
            except Exception as exc:
                last_exc = exc
                selection_prompt = self._retry_prompt(selection_prompt, raw, str(exc))

        raise RuntimeError(
            f"LLM failed to produce a valid action after {self.MAX_ATTEMPTS} attempts. "
            f"Last error: {last_exc}\n"
            f"Last raw response:\n{last_raw}"
        )

    def _record_last_selection(self, action_selection: Action_Selection, info: dict) -> None:
        self._last_action = action_selection
        self._last_info = {**info, "_last_action": action_selection}

    def _record_observation(self, observation: Observation) -> None:
        observation_text = self._truncate_text(str(observation), self.max_stored_observation_chars)
        self.observation_history.append(observation_text)
        if len(self.observation_history) > self.observation_memory_window:
            overflow = self.observation_history[: -self.observation_memory_window]
            self._update_observation_summary(overflow)
            self.observation_history = self.observation_history[-self.observation_memory_window :]

    def _update_observation_summary(self, observations: list[str]) -> None:
        summary_lines: list[str] = []
        if self.observation_summary:
            summary_lines.append(self.observation_summary)

        for observation_text in observations:
            summary_lines.append(self._summarize_observation_text(observation_text))

        self.observation_summary = "\n".join(line for line in summary_lines if line).strip() or None

    def _summarize_observation_text(self, observation_text: str) -> str:
        summary_parts = []
        reward_match = re.search(r"REWARD THIS TURN:\s*(.*)", observation_text)
        if reward_match:
            summary_parts.append(f"reward={reward_match.group(1).strip()}")

        state_lines = []
        in_state_block = False
        for line in observation_text.splitlines():
            stripped = line.strip()
            if stripped == "YOUR STATE:":
                in_state_block = True
                continue
            if in_state_block and not stripped:
                break
            if in_state_block and (
                stripped.startswith("name:")
                or stripped.startswith("position:")
                or stripped.startswith("health:")
                or stripped.startswith("inventory:")
            ):
                state_lines.append(stripped)

        action_lines = [
            line.strip() for line in observation_text.splitlines() if line.strip().startswith("[") and "]" in line
        ]
        if action_lines:
            summary_parts.append(f"actions={', '.join(action_lines[:3])}")
        if state_lines:
            summary_parts.extend(state_lines[:4])

        if not summary_parts:
            summary_parts.append(observation_text.strip().splitlines()[0][:160])

        return " | ".join(summary_parts)

    # -----------------------------------------------------------------------
    # Prompt builders
    # -----------------------------------------------------------------------

    def _observation_memory_block(self) -> str:
        sections = []
        if self.observation_summary:
            sections.append(f"OLDER OBSERVATION SUMMARY:\n{self.observation_summary}")

        if not self.observation_history:
            return "\n\n".join(sections) + ("\n\n" if sections else "")

        entries = "\n\n---\n\n".join(
            f"[t-{len(self.observation_history) - i}]\n{obs}" for i, obs in enumerate(self.observation_history)
        )
        sections.append(f"RECENT OBSERVATIONS (oldest to most recent):\n{entries}")
        return "\n\n".join(sections) + "\n\n"

    def _conversation_memory_block(self) -> str:
        if not self.conversation_history:
            return ""

        relevant_entries = []
        for entry in self.conversation_history[-self.conversation_memory_window :]:
            role = entry.get("role")
            if role == "user":
                relevant_entries.append(
                    f"- received: {self._truncate_text(entry['content'], self.max_stored_message_chars)}"
                )
            elif role == "system":
                relevant_entries.append(
                    f"- note: {self._truncate_text(entry['content'], self.max_stored_message_chars)}"
                )

        if not relevant_entries:
            return ""

        history_str = "\n".join(relevant_entries)
        return f"RECENT CONVERSATION:\n{history_str}\n\n"

    def _reasoning_prompt(self, observation: Observation) -> str:
        return (
            "You are controlling an agent in a grid-world game.\n"
            "Think step by step about which action the agent should take next.\n"
            "Consider the agent's state, nearby entities, and available actions.\n"
            "Write your reasoning in plain text. Do NOT output JSON yet.\n\n"
            + self._observation_memory_block()
            + self._conversation_memory_block()
            + f"CURRENT OBSERVATION:\n{observation}\n\n"
            + format_action_details(observation.possible_actions)
        )

    def _observation_requires_kwargs(self, observation: Observation) -> bool:
        return any(action_selection.required_kwargs for action_selection in observation.possible_actions)

    def _selection_prompt(self, observation: Observation, reasoning: str | None) -> str:
        reasoning_block = f"\nYour prior reasoning:\n{reasoning}\n" if reasoning else ""
        if self._observation_requires_kwargs(observation):
            example_kwargs = "{}"
            for sel in observation.possible_actions:
                if sel.required_kwargs:
                    example_kwargs = json.dumps({k: f"<{k}>" for k in sel.required_kwargs})
                    break
            required_format = '{"action_choice_idx": <integer>, "action_kwargs": <dict or {}>}'
            example_output = f'{{"action_choice_idx": 0, "action_kwargs": {example_kwargs}}}'
            kwargs_instruction = ""
        else:
            required_format = '{"action_choice_idx": <integer>}'
            example_output = '{"action_choice_idx": 0}'
            kwargs_instruction = (
                "None of the available actions require kwargs. " 'Do not include "action_kwargs" in your response.\n\n'
            )

        return (
            "You are controlling an agent in a grid-world game.\n"
            "Choose exactly ONE action. Reply with ONLY a JSON object — no markdown, no extra text.\n\n"
            "REQUIRED FORMAT:\n"
            + required_format
            + "\n\n"
            + kwargs_instruction
            + f"Example: {example_output}\n\n"
            + self._observation_memory_block()
            + self._conversation_memory_block()
            + f"CURRENT OBSERVATION:\n{observation}\n"
            + reasoning_block
            + "\n"
            + format_action_details(observation.possible_actions)
            + "\n\n"
            + "Your JSON:"
        )

    def _retry_prompt(self, prev_prompt: str, bad_response: str, error: str) -> str:
        return (
            f"{prev_prompt}\n\n"
            f"Your previous response was invalid.\n"
            f"  Response: {bad_response}\n"
            f"  Error: {error}\n\n"
            "Try again. Output ONLY the JSON object."
        )

    def _with_system(self, prompt: str) -> str:
        """
        Prepend the policy-level system prompt for text-only model interfaces.
        """
        if self.system_prompt:
            return f"{self.system_prompt}\n\n{prompt}"
        return prompt

    # -----------------------------------------------------------------------
    # Response parsing
    # -----------------------------------------------------------------------

    def _parse_selection(self, raw: str, observation: Observation) -> Action_Selection:
        parsed = self._extract_json(raw)
        idx = parsed.get("action_choice_idx")

        if not isinstance(idx, int) or not (0 <= idx < len(observation.possible_actions)):
            raise ValueError(f"Invalid action_choice_idx: {idx}")

        action_selection = observation.possible_actions[idx]

        if action_selection.required_kwargs:
            action_selection.action_kwargs = self._parse_action_kwargs(
                action_selection,
                parsed.get("action_kwargs", {}),
            )
        else:
            action_selection.action_kwargs = None

        if not action_selection.is_valid():
            raise ValueError(f"Action [{idx}] is invalid in the current state.")

        return action_selection

    def _action_choice_idx(self, action_selection: Action_Selection, observation: Observation) -> int | None:
        for idx, candidate in enumerate(observation.possible_actions):
            if candidate is action_selection:
                return idx
        return None

    def _extract_json(self, text: str) -> dict:
        text = re.sub(r"```(?:json)?\s*", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in model response.")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("JSON response must be an object.")
        return parsed

    def _parse_action_kwargs(self, action_selection: Action_Selection, raw_kwargs: Any) -> dict:
        if not action_selection.required_kwargs:
            return {}

        if not isinstance(raw_kwargs, dict):
            raise ValueError("'action_kwargs' must be a JSON object.")

        expected_keys = list(action_selection.required_kwargs.keys())
        missing = [key for key in expected_keys if key not in raw_kwargs]
        unexpected = [key for key in raw_kwargs.keys() if key not in action_selection.required_kwargs]
        if missing:
            raise ValueError(f"Missing required arguments: {', '.join(missing)}")
        if unexpected:
            raise ValueError(f"Unexpected arguments: {', '.join(unexpected)}")

        ordered_values = [self._coerce_kwarg_value(raw_kwargs[key]) for key in expected_keys]
        return action_selection.parse_and_validate_kwarg_list("; ".join(ordered_values))

    def _coerce_kwarg_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return json.dumps(value)

    # -----------------------------------------------------------------------
    # Communication_Policy — multi-agent dialogue
    # -----------------------------------------------------------------------

    def start_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        self.conversation_history.clear()
        if info:
            self.conversation_history.append({"role": "system", "content": info})
            # be careful with system prompts
            # dont want the model to over pay attention to the system prompt

    def send_message(self, recipients: list[Entity], env: Environment, info: str | None = None) -> str:
        prompt = self._message_prompt(recipients, env, info)
        response = self.model.generate_text(
            self._with_system(prompt),
            self.message_generation_config,
            max_new_tokens=self.message_max_new_tokens,
        ).strip()
        response = self._truncate_text(response, self.max_stored_message_chars)
        self.conversation_history.append({"role": "assistant", "content": response})
        self._trim_history()
        return response

    def receive_message(self, message: str, sender: Entity, env: Environment) -> None:
        message_text = self._truncate_text(message, self.max_stored_message_chars)
        self.conversation_history.append({"role": "user", "content": f"{sender.name}: {message_text}"})
        self._trim_history()

    def end_conversation(self, participants: list[Entity], env: Environment, info: str | None = None) -> None:
        if info:
            self.conversation_history.append({"role": "system", "content": info})
        self._trim_history()

    def _message_prompt(self, recipients: list[Entity], env: Environment, info: str | None) -> str:
        recipients_str = ", ".join(entity.name for entity in recipients)
        history_str = (
            "\n".join(entry["content"] for entry in self.conversation_history[-self.conversation_memory_window :])
            or "(no prior messages)"
        )
        info_str = f"\nExtra context: {info}\n" if info else ""
        return (
            "You are playing a character in a grid-world game.\n"
            "Write ONE short in-character message. No speaker labels, no quotes.\n\n"
            f"Your character: {self.entity.name}\n"
            f"Recipients: {recipients_str}\n"
            f"Environment: {env.description}\n"
            f"{info_str}"
            f"Conversation so far:\n{history_str}\n\n"
            "Your message:"
        )

    def _trim_history(self) -> None:
        if len(self.conversation_history) > self.conversation_memory_window:
            self.conversation_history = self.conversation_history[-self.conversation_memory_window :]

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 14] + "... [truncated]"
