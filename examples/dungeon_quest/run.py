<<<<<<< HEAD
"""Dungeon quest environment - Run the LLM-controlled example."""
=======
"""Dungeon quest environment - Run the example.

Run with --policy preview to see the hardcoded demo without needing an API key.
"""
>>>>>>> origin/bryan/presets
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from examples.dungeon_quest.environment import DungeonRaidEnv
except ModuleNotFoundError:
    from environment import DungeonRaidEnv

<<<<<<< HEAD
=======
from word_play.presets.action_policies.dungeon_quest_preview_policy import DUNGEON_RAIDER_SEQUENCE
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
>>>>>>> origin/bryan/presets
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.renderers import run_exp

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "experiments" / "logs" / "dungeon_quest"
DEFAULT_MODEL_NAME = "openai/gpt-4o"
DEFAULT_MODEL_KEY = "openrouter_dungeon_quest"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build_system_prompt(agent_name: str) -> str:
    """Generate system prompt for the dungeon quest agent."""
    return """You are controlling a dungeon raider in a partially observed dungeon crawl.
Read the observation literally and do not assume anything outside the currently visible area.
For action selection, reply with ONLY one JSON object in the form {"action_choice_idx": N}.
Never output markdown, prose, or an empty response.
Do not invent coordinates for yourself, enemies, walls, or the exit unless they are explicitly given.
Use only the local directional facts, your starting position for the room, your goals, and the available actions.
Your main goal is to defeat the final boss, the Ash Warden.
Each room must be cleared before you can leave it.
When all enemies in the room are dead, the exit opens.
Stand on the open exit tile and choose Enter the exit to reach the next room.
If enemies remain and are visible, prioritize reaching and killing them.
If no enemies are visible, explore efficiently until you find them or find the open exit.
If you are already standing on the open exit tile, choose Enter the exit immediately.
Choose exactly one valid action from the provided action list."""


def main() -> None:
<<<<<<< HEAD
    parser = argparse.ArgumentParser(description="Run the dungeon quest LLM example.")
    parser.add_argument("--policy", choices=["llm"], default="llm", help="Policy mode to use (only LLM supported).")
=======
    parser = argparse.ArgumentParser(description="Run the dungeon quest example.")
    parser.add_argument(
        "--policy",
        choices=["llm", "preview"],
        default="llm",
        help="Policy mode: llm (default, requires API key) or preview (hardcoded demo)."
    )
>>>>>>> origin/bryan/presets
    parser.add_argument("--tile-size", type=int, default=56, help="Tile size for rendering.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME, help="Model name for LLM mode.")
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY, help="Model key for LLM mode.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL for LLM mode.")
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between auto-stepped frames.")
    parser.add_argument("--no-logs", action="store_true", help="Do not save a replay log.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    args = parser.parse_args()

    env = DungeonRaidEnv()

<<<<<<< HEAD
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
            action_generation_config={"temperature": 0.2},
            message_generation_config={"temperature": 0.4},
            use_chain_of_thought=True,
        ),
        sidebar_width=380,
        keep_logs=not args.no_logs,
        log_path=args.log_path,
        log_root=args.log_dir,
        autoplay=True,
        step_delay=args.delay,
        record_title="Dungeon Quest LLM Example",
        initial_notes=["Dungeon quest demo booted."],
    )
=======
    if args.policy == "preview":
        # Attach hardcoded preview policy to the player agent
        # Find the player agent and assign the raider sequence
        for entity in env.state.entities:
            if entity.name == "Raider":
                entity.policy = Follow_Action_Sequence(DUNGEON_RAIDER_SEQUENCE, skip_invalid_actions=True)

        run_exp(
            env=env,
            policy="preview",
            tile_size=args.tile_size,
            sidebar_width=380,
            keep_logs=not args.no_logs,
            log_path=args.log_path,
            log_root=args.log_dir,
            autoplay=True,
            step_delay=args.delay,
            record_title="Dungeon Quest Preview Demo",
            initial_notes=["Dungeon quest preview demo (no API key needed)."],
        )
>>>>>>> origin/bryan/presets


if __name__ == "__main__":
    main()
