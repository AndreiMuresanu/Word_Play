from __future__ import annotations

from typing import Literal

from word_play.core import Agent_Policy
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.action_policies.random_policy import Random_Policy
from word_play.presets.models import LLM_MODEL_REGISTRY, OpenRouter_Model


PolicyKind = Literal["random", "human", "llm"]
DEFAULT_GENERATION_CONFIG = {"temperature": 0.2}


def register_llm_model(
    model_key: str,
    *,
    model_name: str,
    generation_config: dict | None = None,
) -> None:
    LLM_MODEL_REGISTRY.unload(model_key)
    LLM_MODEL_REGISTRY.register(
        model_key,
        OpenRouter_Model,
        model_name=model_name,
        generation_config=generation_config or DEFAULT_GENERATION_CONFIG.copy(),
    )


def make_policy(
    *,
    policy_kind: PolicyKind,
    model_key: str,
    system_prompt: str,
    observation_memory_window: int = 4,
    conversation_memory_window: int = 4,
) -> Agent_Policy:
    if policy_kind == "llm":
        return LLM_Action_And_Communication_Policy(
            model_key=model_key,
            system_prompt=system_prompt,
            use_chain_of_thought=True,
            observation_memory_window=observation_memory_window,
            conversation_memory_window=conversation_memory_window,
            action_max_new_tokens=512,
        )
    if policy_kind == "human":
        return Human_Takes_Action()
    return Random_Policy()
