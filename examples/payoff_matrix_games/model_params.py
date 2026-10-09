from __future__ import annotations

from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.llm_action_and_communication import (
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.models import Human_Model, LLM_MODEL_REGISTRY, OpenRouter_Model

SUPPORTED_MODEL_MODES = (
    "human_action",
    "human_llm",
    "openrouter_small",
    "openrouter_mid",
    "openrouter_large",
)

OPENROUTER_MODEL_PARAMS = {
    "openrouter_small": {
        "model_name": "meta-llama/llama-3.2-1b-instruct",
        "generation_config": {"temperature": 0.0},
    },
    "openrouter_mid": {
        "model_name": "meta-llama/llama-3.1-8b-instruct",
        "generation_config": {"temperature": 0.0},
    },
    "openrouter_large": {
        "model_name": "openai/gpt-5.4",
        "generation_config": {"temperature": 0.0},
    },
}

OPENROUTER_LARGE_ACTION_GENERATION_CONFIG = {
    "response_format": {"type": "json_object"},
    "reasoning": {"effort": "minimal", "exclude": True},
    "verbosity": "low",
}

DEFAULT_POLICY_PARAMS = {
    "action_max_new_tokens": 512,
    "observation_memory_window": 2,
    "max_stored_observation_chars": 1500,
}


def build_system_prompt(game_name: str) -> str:
    return (
        f"You are playing the game: {game_name}. "
        "Each step you must choose exactly one action from the available actions. "
        'Respond only with JSON: {"action_choice_idx": <integer>}.'
    )


def register_model(model_mode: str, game_name: str) -> str:
    model_key = f"payoff_matrix_{game_name}_{model_mode}"

    if model_mode == "human_llm":
        LLM_MODEL_REGISTRY.register(model_key, Human_Model)
        return model_key

    if model_mode in OPENROUTER_MODEL_PARAMS:
        params = OPENROUTER_MODEL_PARAMS[model_mode]
        LLM_MODEL_REGISTRY.register(
            model_key,
            OpenRouter_Model,
            model_name=params["model_name"],
            system_prompt=build_system_prompt(game_name),
            generation_config=params["generation_config"],
            app_name="Word Play",
        )
        return model_key

    raise ValueError(f"Unsupported model_mode: {model_mode}")


def make_policy(model_mode: str, model_key: str | None):
    if model_mode == "human_action":
        return Human_Takes_Action()

    action_generation_config = None
    if model_mode == "openrouter_large":
        action_generation_config = OPENROUTER_LARGE_ACTION_GENERATION_CONFIG

    return LLM_Action_And_Communication_Policy(
        model_key=model_key,
        action_generation_config=action_generation_config,
        **DEFAULT_POLICY_PARAMS,
    )
