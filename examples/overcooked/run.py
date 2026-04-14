"""Overcooked kitchen environment - Run the example."""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from examples.overcooked.environment import OvercookedKitchenEnv
except ModuleNotFoundError:
    from environment import OvercookedKitchenEnv

from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.renderers import run_exp

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "experiments" / "logs" / "overcooked"
DEFAULT_MODEL_NAME = "openai/gpt-4o-mini"
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
    parser.add_argument("--policy", choices=["preview", "llm"], default="preview", help="Policy mode to use.")
    parser.add_argument("--tile-size", type=int, default=56, help="Tile size for rendering.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Model name for LLM mode.")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY, help="Model key for LLM mode.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL for LLM mode.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between auto-stepped frames (preview mode only).")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    args = parser.parse_args()

    env = OvercookedKitchenEnv()

    is_llm = args.policy == "llm"

    # Note: use_chain_of_thought=True enables simulated reasoning via two-step LLM calls
    # (not native model CoT). This works with any model including gpt-4o-mini.
    run_exp(
        env=env,
        policy=args.policy,
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
        step_delay=0.1 if is_llm else args.delay,
        record_title="Overcooked Kitchen Example" if args.policy == "preview" else "Overcooked Kitchen LLM Example",
        initial_notes=["Overcooked demo booted."],
    )


if __name__ == "__main__":
    main()
