<<<<<<< HEAD
"""Overcooked kitchen environment - Run the example."""
from __future__ import annotations

import argparse
from pathlib import Path
=======
"""Overcooked kitchen environment - Run the preview demo or LLM policy.

Preview mode: hardcoded action sequences - no API key needed.
LLM mode: uses OpenRouter API to power agent decision making.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
sys.path.insert(0, "/Users/iamsogoodlo/Documents/Projects/Word_Play-dev copy/src")
from pathlib import Path
from word_play.core.components import Non_Agent_Policy
>>>>>>> origin/bryan/presets

try:
    from examples.overcooked.environment import OvercookedKitchenEnv
except ModuleNotFoundError:
    from environment import OvercookedKitchenEnv

<<<<<<< HEAD
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
=======
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.action_policies.overcooked_preview_policy import (
    EXPEDITER_SEQUENCE,
    PREP_COOK_SEQUENCE,
)
from word_play.presets.models import Lazy_Model_Handle, LLM_MODEL_REGISTRY, OpenRouter_Model, Human_Model
>>>>>>> origin/bryan/presets
from word_play.presets.renderers import run_exp

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "experiments" / "logs" / "overcooked"
DEFAULT_MODEL_NAME = "openai/gpt-4o-mini"
<<<<<<< HEAD
DEFAULT_MODEL_KEY = "openrouter_overcooked"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build_system_prompt(agent_name: str) -> str:
    """Generate system prompt for the overcooked agent."""
    base = """You are controlling a chef in a cooperative overcooked kitchen.
            Read the observation literally and choose exactly one valid action from the provided action list.
            For action selection, reply with ONLY one JSON object in the form {"action_choice_idx": N}.
            Never output markdown, prose, or an empty response.
            Your kitchen goal is to complete every queued Garden Skillet before the kitchen closes.
            Recipe: collect tomato and protein, chop each ingredient on the chopping board, load chopped tomato and chopped protein into the stove, wait for the stove to finish cooking, pick up the finished garden_skillet, and deliver it at the delivery hatch.
            Prioritize whatever advances the current order immediately.
            If you are holding a raw ingredient, move it toward the chopping board.
            If you are holding a chopped ingredient and the stove still needs it, move it to the stove.
            If the stove is cooking, use the time to prepare the next useful ingredient or clear the pass.
            If the stove output is ready, prioritize collecting the finished dish.
            If you are holding the finished dish, serve it immediately.
            Use the chat action to coordinate with the other chef.
            Keep messages very short and concrete."""
    if agent_name == "Prep Cook":
        return base + " You are the Prep Cook. Focus on fetching/chopping ingredients, staging on counters, telling Expediter what's ready."
    if agent_name == "Expediter":
        return base + " You are the Expediter. Focus on loading stove, collecting/serving dishes, telling Prep Cook what the kitchen needs."
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the overcooked kitchen example.")
    parser.add_argument("--policy", choices=["llm"], default="llm", help="Policy mode to use (only LLM supported).")
    parser.add_argument("--tile-size", type=int, default=56, help="Tile size for rendering.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Model name for LLM mode.")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY, help="Model key for LLM mode.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL for LLM mode.")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between auto-stepped frames.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
=======
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

AGENT_MODEL_KEYS = ["prep_cook_model", "expediter_model"]


def build_system_prompt(agent_name: str) -> str:
    """Generate system prompt for the kitchen agent."""
    if agent_name == "Prep Cook":
        return """You are a Prep Cook in a kitchen. Your job is to prepare ingredients.
                Look at the kitchen layout, identify what ingredients are needed (tomato, protein),
                and chop them at the Chopping Board. Then pass them to the Expediter.
                Reply with ONLY a JSON object: {"action_choice_idx": N} where N is the action index."""
    return """You are an Expediter in a kitchen. Your job is to assemble and serve dishes.
            Collect prepared ingredients from the Pass Counter, cook them on the Stove,
            plate them at the Plate Stack, and serve at the Delivery Hatch.
            Reply with ONLY a JSON object: {"action_choice_idx": N} where N is the action index."""


def register_models(model_name: str, use_human: bool = False) -> list[str]:
    """Register models for both agents."""
    if use_human:
        for key in AGENT_MODEL_KEYS:
            LLM_MODEL_REGISTRY[key] = Lazy_Model_Handle(lambda: Human_Model())
        return AGENT_MODEL_KEYS

    # Register OpenRouter models for each agent with their own system prompts
    for i, key in enumerate(AGENT_MODEL_KEYS):
        agent_name = "Prep Cook" if i == 0 else "Expediter"
        # Use closure to capture agent_name by value
        def make_loader(name=agent_name):
            return OpenRouter_Model(
                model_name=model_name,
                system_prompt=build_system_prompt(name),
                generation_params={"temperature": 0.3},
                app_name="Word Play Overcooked",
            )
        LLM_MODEL_REGISTRY[key] = Lazy_Model_Handle(make_loader)

    return AGENT_MODEL_KEYS


def build_llm_policy(model_key: str) -> LLM_Action_And_Communication_Policy:
    """Build an LLM policy for an agent."""
    return LLM_Action_And_Communication_Policy(
        model_key=model_key,
        action_generation_config={"temperature": 0.3},
        use_chain_of_thought=True,
        observation_memory_window=3,
    )

def attach_preview_policies(env: OvercookedKitchenEnv) -> None:
    """Attach hardcoded preview policies to both agents."""
    for entity in env.state.entities:
        if entity.name == "Prep Cook":
            policy = Follow_Action_Sequence(PREP_COOK_SEQUENCE, skip_invalid_actions=True)
            entity.components[Non_Agent_Policy] = policy
            policy.entity = entity
            entity.is_agent = False
        elif entity.name == "Expediter":
            policy = Follow_Action_Sequence(EXPEDITER_SEQUENCE, skip_invalid_actions=True)
            entity.components[Non_Agent_Policy] = policy
            policy.entity = entity
            entity.is_agent = False

    env._init_agent_list()
    env._init_agent_idx_dict()
    import copy as copy_module
    env.initial_state = copy_module.deepcopy(env.state)


def llm_policy_builder(env, agent, model_key: str):
    """Build LLM policy for agent - matches run_exp signature."""
    # Map agent name to the specific model key registered for that agent
    if agent.name == "Prep Cook":
        return build_llm_policy(AGENT_MODEL_KEYS[0])
    else:
        return build_llm_policy(AGENT_MODEL_KEYS[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the overcooked kitchen demo.")
    parser.add_argument("--policy", choices=["preview", "llm"], default="preview",
                        help="Policy mode: preview (hardcoded) or llm (requires API key).")
    parser.add_argument("--tile-size", type=int, default=56, help="Tile size for rendering.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between auto-stepped frames.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Model name for LLM mode.")
    parser.add_argument("--human", action="store_true", help="Use human input instead of LLM API.")
>>>>>>> origin/bryan/presets
    args = parser.parse_args()

    env = OvercookedKitchenEnv()

<<<<<<< HEAD
    # Note: use_chain_of_thought=True enables simulated reasoning via two-step LLM calls
    # (not native model CoT). This works with any model including gpt-4o-mini.
    run_exp(
        env=env,
        policy="llm",
        tile_size=args.tile_size,
        model_name=args.model_name,
        model_key=args.model_key,
        base_url=args.base_url,
        llm_policy_builder=lambda _env, agent, model_key: LLM_Action_And_Communication_Policy(
            model_key=model_key,
            system_prompt=build_system_prompt(agent.name),
            action_generation_config={"temperature": 0.25},
            message_generation_config={"temperature": 0.4},
            reasoning_generation_config={"temperature": 0.2, "max_tokens": 256},
            use_chain_of_thought=True,
        ),
        sidebar_width=380,
        keep_logs=not args.no_logs,
        log_path=args.log_path,
        log_root=args.log_dir,
        autoplay=True,
        step_delay=args.delay,
        record_title="Overcooked Kitchen LLM Example",
        initial_notes=["Overcooked demo booted."],
    )
=======
    if args.policy == "preview":
        attach_preview_policies(env)
        run_exp(
            env=env,
            tile_size=args.tile_size,
            sidebar_width=380,
            keep_logs=not args.no_logs,
            log_path=args.log_path,
            log_root=args.log_dir,
            autoplay=not args.paused,
            step_delay=args.delay,
            record_title="Overcooked Kitchen Preview Demo",
            initial_notes=["Overcooked preview demo - hardcoded action sequences (no API key needed)."],
        )
    else:  # llm mode
        # Check if all model keys have models registered
        if not all(k in LLM_MODEL_REGISTRY for k in AGENT_MODEL_KEYS):
            register_models(args.model_name, use_human=args.human)

        run_exp(
            env=env,
            policy="llm",
            tile_size=args.tile_size,
            sidebar_width=420,
            keep_logs=not args.no_logs,
            log_path=args.log_path,
            log_root=args.log_dir,
            autoplay=not args.paused,
            step_delay=args.delay,
            model_name=args.model_name,
            model_key="dummy",  # Not used since we register models ourselves
            base_url=DEFAULT_BASE_URL,
            llm_policy_builder=llm_policy_builder,
            record_title="Overcooked Kitchen LLM Demo",
            initial_notes=["Overcooked with LLM agents - both agents making decisions."],
        )
>>>>>>> origin/bryan/presets


if __name__ == "__main__":
    main()
