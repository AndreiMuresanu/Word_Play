"""
wordplay_inspect_bridge.py
--------------------------
Bridges Wordplay's gym-like Environment API to Inspect's evaluation framework.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Sequence

from inspect_ai import Task, task
from inspect_ai.dataset import Dataset, MemoryDataset, Sample
from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    ModelOutput,
    get_model,
)
from inspect_ai.scorer import Score, Scorer, mean, scorer, stderr
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, ToolError, tool
from inspect_ai.util import input_screen, store_as, StoreModel

from pydantic import Field


# ---------------------------------------------------------------------------
# 1.  Per-sample state model — stored cleanly in Inspect's store
# ---------------------------------------------------------------------------

class WordplayEpisodeState(StoreModel):
    """All episode-level state for one Wordplay sample."""

    # Live env reference (not JSON-serialisable, so we store as Any)
    env: Any = Field(default=None, exclude=True)

    step_count: int = Field(default=0)
    done: bool = Field(default=False)

    # Cumulative rewards per agent, accumulated across all steps
    cumulative_rewards: list[float] = Field(default_factory=list)

    # Full trajectory for Inspect View: list of step dicts
    trajectory: list[dict[str, Any]] = Field(default_factory=list)

    # Per-agent message histories kept here so they feed into the transcript
    agent_histories: list[list[dict[str, Any]]] = Field(default_factory=list)


# Convenience helpers
def _ep(state: TaskState) -> WordplayEpisodeState:
    return store_as(WordplayEpisodeState)


# ---------------------------------------------------------------------------
# 2.  Action parsing — strict integer index
# ---------------------------------------------------------------------------

def _format_possible_actions(possible_actions) -> str:
    return "\n".join(
        f"  [{i}] {action_sel}" for i, action_sel in enumerate(possible_actions)
    )


def _parse_action_index(raw: str, possible_actions) -> Any:
    """
    Parse the model's response as an integer action index.
    Accepts:
      - A bare integer string: "2"
      - An integer inside brackets: "[2]"
      - Falls back to 0 on any parse failure.
    """
    raw = raw.strip().strip("[]").strip()
    try:
        idx = int(raw)
        if 0 <= idx < len(possible_actions):
            return possible_actions[idx]
    except (ValueError, TypeError):
        pass
    # Fallback: first action
    return possible_actions[0] if possible_actions else None


# ---------------------------------------------------------------------------
# 3.  Custom @tool — per-agent, uses integer index selection
# ---------------------------------------------------------------------------

def make_wordplay_action_tool(agent_id: int, shared: dict) -> Tool:
    """
    Returns a @tool called `wordplay_action` for one agent.
    The model is asked to pass an integer index corresponding to the listed
    possible actions. The chosen Action_Selection is stored in shared["pending"].
    """

    @tool
    def wordplay_action():
        async def execute(action_index: int) -> str:
            """
            Take an action in the Wordplay environment by specifying its index.

            Args:
                action_index: The integer index of the action you want to take,
                              as listed in the "Possible actions" section of
                              your observation (e.g. 0, 1, 2, ...).

            Returns:
                Confirmation that the action has been queued.
            """
            env = shared.get("env")
            if env is None:
                raise ToolError("Environment not initialised yet.")

            possible = env.get_possible_actions(agent_id)
            if not possible:
                raise ToolError("No actions available — episode may have ended.")

            if not (0 <= action_index < len(possible)):
                raise ToolError(
                    f"Invalid index {action_index}. "
                    f"Valid range: 0–{len(possible) - 1}. "
                    f"Please choose again.\n{_format_possible_actions(possible)}"
                )

            shared.setdefault("pending", {})[agent_id] = possible[action_index]
            return f"Action [{action_index}] '{possible[action_index]}' queued for agent {agent_id}."

        return execute

    return wordplay_action()


# ---------------------------------------------------------------------------
# 4.  Core solver
# ---------------------------------------------------------------------------

@solver
def wordplay_episode_solver(
    env_factory: Callable[[], Any],
    opponent_model: str | None = None,
    max_steps: int = 50,
    system_prompt_template: str = (
        "You are playing in a multi-agent text environment.\n"
        "Environment: {env_description}\n"
        "You are Agent {agent_id}. On each turn you will receive an observation "
        "and a numbered list of possible actions.\n"
        "Call the `wordplay_action` tool with the INTEGER INDEX of the action "
        "you want to take. Do not output any text — only call the tool.\n"
        "Play to win."
    ),
    discussion_turns: int = 0,
) -> Solver:
    """
    Main solver that drives a full Wordplay episode.

    Args:
        env_factory:    Zero-arg callable returning a fresh Wordplay Environment.
                        Called once per Sample so episodes are independent.
        opponent_model: Inspect model string for agents 1+ (e.g. "openai/gpt-4o").
                        If None, uses the same model as the subject (agent 0).
        max_steps:      Hard truncation cap on environment steps.
        system_prompt_template: f-string template; receives {env_description}
                        and {agent_id}.
        discussion_turns: Rounds of discussion before each action phase.
                          Set >0 only for Discussion_Phase_With_Reset_Environment.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # ---- boot env ----
        env = env_factory()
        env.reset(seed=state.metadata.get("seed"))

        ep = _ep(state)
        ep.env = env
        ep.done = False
        ep.step_count = 0
        ep.cumulative_rewards = [0.0] * len(env.agents)
        ep.trajectory = []
        ep.agent_histories = [[] for _ in env.agents]

        # Shared side-channel: env ref + pending action slots
        shared: dict[str, Any] = {"env": env, "pending": {}}

        # Resolve models
        subject_model = get_model()
        opp_model = get_model(opponent_model) if opponent_model else subject_model
        agent_models = [subject_model] + [opp_model] * (len(env.agents) - 1)

        # Build message histories and tools per agent
        agent_histories: list[list[ChatMessage]] = []
        agent_tools: list[list[Tool]] = []
        for i in range(len(env.agents)):
            sys_prompt = system_prompt_template.format(
                env_description=env.properties.description,
                agent_id=i,
            )
            agent_histories.append([ChatMessageSystem(content=sys_prompt)])
            agent_tools.append([make_wordplay_action_tool(i, shared)])

        # ---- episode loop ----
        for step_idx in range(max_steps):
            if all(env.terminations) or all(env.truncations):
                break

            # ---- optional discussion phase ----
            if discussion_turns > 0 and hasattr(env, "start_new_discussion_phase"):
                env.start_new_discussion_phase()
                disc_log: list[dict] = []
                for disc_turn in range(discussion_turns):
                    for agent_id in range(len(env.agents)):
                        obs = env.observe(agent_id)
                        disc_prompt = (
                            f"[Discussion turn {disc_turn + 1}/{discussion_turns}]\n"
                            f"Observation:\n{obs}\n\n"
                            "Reply with your discussion message (plain text, no tool call)."
                        )
                        agent_histories[agent_id].append(
                            ChatMessageUser(content=disc_prompt)
                        )
                        response = await agent_models[agent_id].generate(
                            agent_histories[agent_id],
                            config=GenerateConfig(max_tokens=256),
                        )
                        msg_text = response.message.text
                        agent_histories[agent_id].append(response.message)
                        env.submit_message(agent_id, msg_text)
                        disc_log.append({"agent": agent_id, "turn": disc_turn, "message": msg_text})
                    env.end_discussion_phase_turn()
                env.end_discussion_phase()
                ep.trajectory.append({"step": step_idx, "phase": "discussion", "messages": disc_log})

            # ---- action phase: gather actions from all agents concurrently ----
            shared["pending"] = {}

            action_tasks = [
                _run_agent_action(
                    model=agent_models[agent_id],
                    history=agent_histories[agent_id],
                    tools=agent_tools[agent_id],
                    agent_id=agent_id,
                    shared=shared,
                    env=env,
                    step_idx=step_idx,
                )
                for agent_id in range(len(env.agents))
            ]
            results = await asyncio.gather(*action_tasks)
            for agent_id, new_msgs in enumerate(results):
                agent_histories[agent_id].extend(new_msgs)

            # ---- collect chosen actions and step env ----
            action_selections = []
            for agent_id in range(len(env.agents)):
                possible = env.get_possible_actions(agent_id)
                chosen = shared["pending"].get(
                    agent_id, possible[0] if possible else None
                )
                action_selections.append(chosen)

            env.step(action_selections)
            ep.step_count += 1

            # Accumulate rewards
            for agent_id in range(len(env.agents)):
                r = env.last_rewards[agent_id] if env.last_rewards else 0.0
                ep.cumulative_rewards[agent_id] += float(r or 0.0)

            # Record step in trajectory (this is what Inspect View will show)
            step_record = {
                "step": step_idx + 1,
                "actions": [str(a) for a in action_selections],
                "rewards": list(env.last_rewards or []),
                "terminations": list(env.terminations),
            }
            ep.trajectory.append(step_record)

            # Append step summary to state.messages so it shows in the main
            # Inspect sample transcript for agent 0 (the subject model)
            obs0, reward0, term0, trunc0, _ = env.last(0)
            state.messages.append(
                ChatMessageUser(
                    content=(
                        f"[Step {step_idx + 1}] "
                        f"Reward: {reward0} | "
                        f"Cumulative: {ep.cumulative_rewards[0]:.3f} | "
                        f"Terminated: {term0} | "
                        f"Actions: {[str(a) for a in action_selections]}"
                    )
                )
            )

            if term0 or trunc0:
                break

        ep.done = True

        # Write a summary assistant message so state.output is set
        # Use ModelOutput.from_content() — safe whether or not output was set before
        summary = json.dumps(
            {
                "cumulative_rewards": ep.cumulative_rewards,
                "steps": ep.step_count,
                "terminations": env.terminations,
            },
            indent=2,
        )
        state.output = ModelOutput.from_content(
            model=str(state.model),
            content=summary,
        )

        return state

    return solve


async def _run_agent_action(
    model,
    history: list[ChatMessage],
    tools: list[Tool],
    agent_id: int,
    shared: dict,
    env,
    step_idx: int,
) -> list[ChatMessage]:
    """
    Ask one agent to pick an action via integer index. Runs a short
    generate_loop so the model can make the tool call.
    Returns the new messages to append to this agent's history.
    """
    obs = env.observe(agent_id)
    possible = env.get_possible_actions(agent_id)
    action_prompt = (
        f"[Step {step_idx + 1}]\n"
        f"Observation:\n{obs}\n\n"
        f"Possible actions:\n{_format_possible_actions(possible)}\n\n"
        "Call `wordplay_action` with the INTEGER INDEX of your chosen action."
    )
    history.append(ChatMessageUser(content=action_prompt))

    new_messages, _ = await model.generate_loop(
        history,
        tools=tools,
        config=GenerateConfig(max_tokens=256),
    )

    # Safety net: if the model never called the tool, default to index 0
    if agent_id not in shared.get("pending", {}):
        if possible:
            shared.setdefault("pending", {})[agent_id] = possible[0]

    return new_messages


# ---------------------------------------------------------------------------
# 5.  Scorer — uses cumulative rewards tracked in store
# ---------------------------------------------------------------------------

@scorer(metrics=[mean(), stderr()])
def wordplay_outcome_scorer(
    agent_id: int = 0,
    score_fn: Callable[[Any, int, "WordplayEpisodeState"], float] | None = None,
) -> Scorer:
    """
    Scores the episode from the perspective of `agent_id` (default: 0).

    Default: score = cumulative reward for agent_id accumulated across all
    steps of the episode (tracked in WordplayEpisodeState.cumulative_rewards).

    Custom scoring: pass `score_fn(env, agent_id, ep_state) -> float` to
    implement any domain-specific logic (e.g. binary win/loss, normalised score).

    Args:
        agent_id: Which agent to score from.
        score_fn: Optional callable(env, agent_id, ep_state) -> float.
    """

    async def score(state: TaskState, target) -> Score:
        ep = store_as(WordplayEpisodeState)
        env = ep.env

        if env is None:
            return Score(
                value=0.0,
                explanation="Environment not found in store — episode may not have run.",
            )

        if score_fn is not None:
            value = float(score_fn(env, agent_id, ep))
            explanation = f"Custom score_fn result: {value}"
        else:
            cum_reward = (
                ep.cumulative_rewards[agent_id]
                if ep.cumulative_rewards and agent_id < len(ep.cumulative_rewards)
                else 0.0
            )
            value = cum_reward
            explanation = (
                f"Agent {agent_id} cumulative reward: {cum_reward:.4f} | "
                f"Steps: {ep.step_count} | "
                f"Terminated: {env.terminations[agent_id]}"
            )

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "cumulative_rewards": ep.cumulative_rewards,
                "last_rewards": env.last_rewards,
                "terminations": env.terminations,
                "steps": ep.step_count,
                "trajectory_length": len(ep.trajectory),
            },
        )

    return score


# ---------------------------------------------------------------------------
# 6.  Human baseline solver
# ---------------------------------------------------------------------------

@solver
def wordplay_human_baseline_solver(
    env_factory: Callable[[], Any],
    max_steps: int = 50,
) -> Solver:
    """
    Human baseline solver: presents observations to a human in the terminal
    using Inspect's input_screen() and reads their action choice as an integer.

    Run with:
        inspect eval your_task.py --solver=wordplay_human_baseline_solver \\
            --model anthropic/claude-3-5-haiku-latest
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        env = env_factory()
        env.reset(seed=state.metadata.get("seed"))

        ep = _ep(state)
        ep.env = env
        ep.cumulative_rewards = [0.0] * len(env.agents)

        from rich.prompt import Prompt

        for step_idx in range(max_steps):
            if all(env.terminations) or all(env.truncations):
                break

            action_selections = []
            for agent_id in range(len(env.agents)):
                obs = env.observe(agent_id)
                possible = env.get_possible_actions(agent_id)

                with input_screen() as console:
                    console.print(
                        f"\n[bold cyan]=== Step {step_idx + 1} | Agent {agent_id} ===[/bold cyan]"
                    )
                    console.print(f"[yellow]Observation:[/yellow]\n{obs}\n")
                    console.print("[yellow]Possible actions:[/yellow]")
                    for i, a in enumerate(possible):
                        console.print(f"  [{i}] {a}")

                    raw = Prompt.ask("Enter action index", default="0")

                try:
                    idx = int(raw.strip())
                    chosen = possible[idx] if 0 <= idx < len(possible) else possible[0]
                except (ValueError, IndexError):
                    chosen = possible[0]

                action_selections.append(chosen)

            env.step(action_selections)
            ep.step_count += 1

            for agent_id in range(len(env.agents)):
                r = env.last_rewards[agent_id] if env.last_rewards else 0.0
                ep.cumulative_rewards[agent_id] += float(r or 0.0)

            obs0, reward0, term0, trunc0, _ = env.last(0)
            state.messages.append(
                ChatMessageUser(
                    content=f"[Step {step_idx + 1}] Reward: {reward0} | Done: {term0}"
                )
            )
            if term0 or trunc0:
                break

        ep.done = True
        state.output = ModelOutput.from_content(
            model="human",
            content=json.dumps({"cumulative_rewards": ep.cumulative_rewards, "steps": ep.step_count}),
        )
        return state

    return solve


# ---------------------------------------------------------------------------
# 7.  Dataset builder
# ---------------------------------------------------------------------------

def wordplay_dataset(
    seeds: Sequence[int] | None = None,
    configs: Sequence[dict] | None = None,
) -> Dataset:
    """
    Builds an Inspect MemoryDataset from seeds or config dicts.
    Each seed / config becomes one Sample (= one episode).

    Args:
        seeds:   List of ints — one episode per seed.
        configs: List of dicts with at least {"seed": int}.
                 Takes precedence over seeds if both provided.
    """
    if configs:
        samples = [
            Sample(
                input=f"Episode config: {cfg}",
                metadata=cfg,
                id=str(cfg.get("seed", i)),
            )
            for i, cfg in enumerate(configs)
        ]
    elif seeds:
        samples = [
            Sample(input=f"Episode seed={s}", metadata={"seed": s}, id=str(s))
            for s in seeds
        ]
    else:
        samples = [Sample(input="Episode seed=42", metadata={"seed": 42}, id="0")]

    return MemoryDataset(samples)