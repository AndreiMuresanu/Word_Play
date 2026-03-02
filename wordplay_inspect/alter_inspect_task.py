"""
altar_inspect_task.py
---------------------
Runnable Inspect eval tasks for the Unreliable Altar environment.

Run it:
    inspect eval altar_inspect_task.py --model anthropic/claude-3-5-haiku-latest

Different opponent:
    inspect eval altar_inspect_task.py --model anthropic/claude-3-5-sonnet-latest \\
        -T opponent_model=openai/gpt-4o-mini

Human baseline (you play agent 0):
    inspect eval altar_inspect_task.py@altar_human_baseline \\
        --model anthropic/claude-3-5-haiku-latest

Human tool approval (LLM proposes, you approve each action):
    inspect eval altar_inspect_task.py --model anthropic/claude-3-5-haiku-latest \\
        --approval human

View results:
    inspect view
"""

from inspect_ai import Task, task

from wordplay_inspect_bridge import (
    wordplay_dataset,
    wordplay_episode_solver,
    wordplay_human_baseline_solver,
    wordplay_outcome_scorer,
    WordplayEpisodeState,
)


# ---------------------------------------------------------------------------
# Environment factory — swap this out for any other Wordplay env
# ---------------------------------------------------------------------------

def _make_altar_env():
    from environments.altar.unreliable_altar.env import Unreliable_Altar_Env
    return Unreliable_Altar_Env(
        num_agents=2,
        discussion_phase_turn_count=3,
    )


# ---------------------------------------------------------------------------
# Task 1: Standard LLM eval
# ---------------------------------------------------------------------------

@task
def altar_eval(
    opponent_model: str | None = None,
    max_steps: int = 20,
    num_seeds: int = 5,
    discussion_turns: int = 3,
):
    """
    Evaluate LLM agents in the Unreliable Altar environment.

    The subject model (--model) plays as agent 0.
    opponent_model plays as agent 1 (defaults to same model as agent 0).
    """
    return Task(
        dataset=wordplay_dataset(seeds=list(range(num_seeds))),
        solver=wordplay_episode_solver(
            env_factory=_make_altar_env,
            opponent_model=opponent_model,
            max_steps=max_steps,
            discussion_turns=discussion_turns,
        ),
        scorer=wordplay_outcome_scorer(agent_id=0),
    )


# ---------------------------------------------------------------------------
# Task 2: Human baseline
# ---------------------------------------------------------------------------

@task
def altar_human_baseline(max_steps: int = 20, num_seeds: int = 1):
    """Human baseline — you play agent 0 in the terminal."""
    return Task(
        dataset=wordplay_dataset(seeds=[42]),
        solver=wordplay_human_baseline_solver(
            env_factory=_make_altar_env,
            max_steps=max_steps,
        ),
        scorer=wordplay_outcome_scorer(agent_id=0),
    )


# ---------------------------------------------------------------------------
# Task 3: Head-to-head with custom win/loss scorer
# ---------------------------------------------------------------------------

@task
def altar_head_to_head(
    opponent_model: str = "openai/gpt-4o-mini",
    max_steps: int = 20,
    num_seeds: int = 10,
):
    """
    Run subject model (--model) as agent 0 vs opponent_model as agent 1.
    Score = 1.0 if agent 0's cumulative reward > agent 1's, else 0.0.

    To get a symmetric result, run twice with roles swapped:
        inspect eval altar_inspect_task.py@altar_head_to_head \\
            --model model_a -T opponent_model=model_b
        inspect eval altar_inspect_task.py@altar_head_to_head \\
            --model model_b -T opponent_model=model_a
    """
    def win_loss(env, agent_id, ep: WordplayEpisodeState) -> float:
        if not ep.cumulative_rewards or len(ep.cumulative_rewards) < 2:
            return 0.0
        return 1.0 if ep.cumulative_rewards[0] > ep.cumulative_rewards[1] else 0.0

    return Task(
        dataset=wordplay_dataset(seeds=list(range(num_seeds))),
        solver=wordplay_episode_solver(
            env_factory=_make_altar_env,
            opponent_model=opponent_model,
            max_steps=max_steps,
            discussion_turns=3,
        ),
        scorer=wordplay_outcome_scorer(agent_id=0, score_fn=win_loss),
    )