from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from examples.overcooked.environment import (  # noqa: E402
    KitchenLayoutAdapter,
    OvercookedKitchenEnv,
    SinglePlayerOvercookedEnv,
)
from word_play.core import Agent_Policy  # noqa: E402
from word_play.presets.action_policies.llm_action_and_communication import (  # noqa: E402
    LLM_Action_And_Communication_Policy,
)
from word_play.presets.models import OpenRouter_Model, register_model  # noqa: E402
from word_play.presets.renderers import PygameRenderer  # noqa: E402

DEFAULT_LOG_DIR = PROJECT_ROOT / "experiments" / "logs" / "overcooked"


def _compact_lines(text: str, limit: int = 4) -> list[str]:
    """Return a few non-empty lines from an observation string."""
    return [line.strip() for line in text.splitlines() if line.strip()][:limit]


def _compact_action_lines(observation) -> list[str]:
    """Return the full numbered list of currently available actions."""
    return [f"[{idx}] {selection}" for idx, selection in enumerate(observation.possible_actions)]


def _build_hud(agent_name: str, env, observation_summary: dict | None = None, action_info: dict | None = None) -> None:
    """Update the renderer HUD with the LLM's current observation and selected action."""
    sidebar_lines = [f"Chef: {agent_name}"]
    sidebar_lines.append("Agent Thought Process:")
    if action_info is not None and action_info.get("reasoning"):
        sidebar_lines.extend([line for line in str(action_info["reasoning"]).splitlines() if line.strip()])
    else:
        sidebar_lines.append("(no explicit reasoning returned)")

    if observation_summary is not None:
        sidebar_lines.append("Possible Actions:")
        sidebar_lines.extend(observation_summary["actions"])

    env.hud_sidebar_header = "Agent"
    env.hud_sidebar_lines = sidebar_lines[:32]
    env.hud_sidebar_width = 620


def _system_prompt_for(agent_name: str, single_player: bool) -> str:
    base_prompt = (
        "You are controlling a chef in a sparse-reward overcooked kitchen. "
        "Read the observation literally and choose exactly one valid action from the provided action list. "
        "Your goal is to complete every ticket before the kitchen closes. "
        "The current recipe is Garden Skillet: 1 chopped tomato plus 1 chopped protein into the stove, "
        "wait until it finishes cooking, then put the cooked dish on a plate and serve it at the delivery hatch. "
        "If you are holding a raw ingredient, move it to the chopping board. "
        "If you are holding a chopped ingredient and the pot still needs it, move it to the stove. "
        "If the pot is ready and you can get a plate, prioritize plating. "
        "If you are holding the finished dish, go serve it immediately. "
        "Use the order queue, pot status, held item, nearby stations, and staged counter items to decide what to do. "
        "Do not invent actions. Choose only from the provided action list."
    )
    if single_player:
        return (
            base_prompt
            + " You are the only chef, so you must handle prep, cooking, plating, and service end to end."
        )
    if agent_name == "Prep Cook":
        return (
            base_prompt
            + " You are the Prep Cook on the left side. Focus on fetching ingredients, chopping them, and staging them on the pass or divider counters so the expediter can keep service moving."
        )
    if agent_name == "Expediter":
        return (
            base_prompt
            + " You are the Expediter on the right side. Focus on clearing the pass, loading the stove, grabbing plates, plating finished dishes, and serving completed orders."
        )
    return base_prompt


def build_llm_overcooked_env(
    *,
    model_key: str,
    renderer: PygameRenderer | None = None,
    single_player: bool = False,
):
    """Create the overcooked env and replace scripted policies with LLM policies."""
    env_type = SinglePlayerOvercookedEnv if single_player else OvercookedKitchenEnv
    env = env_type(renderer=renderer)

    for agent in env.agents:
        components = {
            ctype: component
            for ctype, component in agent.components.items()
            if not isinstance(component, Agent_Policy)
        }
        policy = LLM_Action_And_Communication_Policy(
            model_key=model_key,
            system_prompt=_system_prompt_for(agent.name, single_player),
            action_generation_config={"temperature": 0.2},
            message_generation_config={"temperature": 0.3},
            reasoning_generation_config={"temperature": 0.2},
            use_chain_of_thought=True,
        )
        policy.entity = agent
        components[type(policy)] = policy
        agent.components = components
        agent.is_agent = True

    original_end_of_step = env.environment_end_of_step

    def wrapped_end_of_step(action_selections):
        original_end_of_step(action_selections)
        if env.agents:
            focus_agent = env.agents[0]
            observation = env.observe(0)
            observation_summary = {
                "summary": " ".join(_compact_lines(str(observation), limit=3)),
                "lines": _compact_lines(str(observation), limit=10),
                "full_text": str(observation),
                "actions": _compact_action_lines(observation),
            }
            latest_action_info = getattr(env, "_latest_llm_action_info", None)
            _build_hud(focus_agent.name, env, observation_summary, latest_action_info)

    env.environment_end_of_step = wrapped_end_of_step

    if env.agents:
        initial_observation = env.observe(0)
        _build_hud(
            env.agents[0].name,
            env,
            {
                "summary": " ".join(_compact_lines(str(initial_observation), limit=3)),
                "lines": _compact_lines(str(initial_observation), limit=10),
                "full_text": str(initial_observation),
                "actions": _compact_action_lines(initial_observation),
            },
        )
    return env


def run_llm_overcooked_example(
    *,
    model_name: str,
    model_key: str,
    base_url: str,
    tile_size: int,
    autoplay: bool,
    render_delay: float,
    log_path: str | None,
    log_dir: str | None,
    single_player: bool,
) -> str | None:
    """Run the live LLM overcooked simulation and return the saved replay pickle path."""
    register_model(
        model_key,
        OpenRouter_Model,
        model_name=model_name,
        generation_config={"temperature": 0.2},
        api_key_env="OPENROUTER_API_KEY",
        base_url=base_url,
    )

    renderer = PygameRenderer(layout=KitchenLayoutAdapter(), tile_size=tile_size)

    def reset_factory():
        return build_llm_overcooked_env(model_key=model_key, renderer=renderer, single_player=single_player)

    def step_builder(env):
        selections = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            observation_summary = {
                "summary": " ".join(_compact_lines(str(observation), limit=3)),
                "lines": _compact_lines(str(observation), limit=10),
                "full_text": str(observation),
                "actions": _compact_action_lines(observation),
            }
            policy = agent.get_component(Agent_Policy)
            selection, info = policy.select_action(observation)
            setattr(env, "_latest_llm_observation_summary", observation_summary)
            action_info = {
                "selection": str(selection),
                "raw_response": info.get("raw_response"),
                "reasoning": info.get("reasoning"),
                "attempt": info.get("attempt"),
            }
            setattr(env, "_latest_llm_action_info", action_info)
            _build_hud(agent.name, env, observation_summary, action_info)
            selections.append(selection)
        return selections

    initial_env = reset_factory()
    record_title = "Overcooked LLM Example" if not single_player else "Overcooked Single-Player LLM Example"
    initial_notes = [
        "Overcooked LLM run booted.",
        "Replay auto-saves to a pickle log.",
    ]
    renderer.run_live_view(
        initial_env,
        step_builder=step_builder,
        keep_logs=True,
        log_path=log_path,
        log_root=log_dir or str(DEFAULT_LOG_DIR),
        record_title=record_title,
        autoplay=autoplay,
        step_delay=render_delay,
        max_steps=initial_env.episode_length,
        reset_factory=reset_factory,
        initial_notes=initial_notes,
    )
    return renderer.last_record_path


def main() -> None:
    """Parse CLI arguments and run the live overcooked LLM example."""
    parser = argparse.ArgumentParser(description="Run the overcooked example with LLM-controlled chefs.")
    parser.add_argument("--model-name", default="openai/gpt-5-mini")
    parser.add_argument("--model-key", default="openrouter_overcooked")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--tile-size", type=int, default=56)
    parser.add_argument("--paused", action="store_true", help="Start paused instead of autoplaying.")
    parser.add_argument("--render-delay", type=float, default=0.28, help="Seconds between auto-stepped frames.")
    parser.add_argument("--log-path", default=None, help="Optional explicit path for the replay log pickle.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for auto-named replay logs.")
    parser.add_argument("--single-player", action="store_true", help="Run the one-chef kitchen variant.")
    args = parser.parse_args()

    saved_log_path = run_llm_overcooked_example(
        model_name=args.model_name,
        model_key=args.model_key,
        base_url=args.base_url,
        tile_size=args.tile_size,
        autoplay=not args.paused,
        render_delay=args.render_delay,
        log_path=args.log_path,
        log_dir=args.log_dir,
        single_player=args.single_player,
    )
    if saved_log_path is not None:
        print(f"Saved replay log: {saved_log_path}")


if __name__ == "__main__":
    main()
