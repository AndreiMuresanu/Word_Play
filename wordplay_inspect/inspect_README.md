# Wordplay × Inspect Integration

Make any Wordplay multi-agent environment compatible with [Inspect](https://inspect.aisi.org.uk), the UK AISI evaluation framework widely used in the AI safety community.

## Files

| File | Purpose |
|---|---|
| `wordplay_inspect_bridge.py` | Reusable bridge layer — not env-specific, copy once |
| `altar_inspect_task.py` | Example task file wiring up the Altar environment |

---

## Quickstart

### 1. Install Inspect

```bash
pip install inspect-ai
```

Optionally install the VS Code extension: search **"Inspect AI"** in the Extensions panel for live log viewing and task running.

### 2. Add the bridge to your project

Copy `wordplay_inspect_bridge.py` anywhere on your Python path (or into the same directory as your task files).

### 3. Create a task file for your environment

```python
# my_env_task.py
from inspect_ai import Task, task
from wordplay_inspect_bridge import (
    wordplay_dataset,
    wordplay_episode_solver,
    wordplay_outcome_scorer,
)
from my_env import MyEnv

def make_env():
    return MyEnv(...)   # called fresh for each Sample

@task
def my_env_eval(opponent_model=None, max_steps=30, num_seeds=5):
    return Task(
        dataset=wordplay_dataset(seeds=list(range(num_seeds))),
        solver=wordplay_episode_solver(
            env_factory=make_env,
            opponent_model=opponent_model,
            max_steps=max_steps,
        ),
        scorer=wordplay_outcome_scorer(agent_id=0),
    )
```

### 4. Run it

```bash
# Agent 0 and agent 1 are both the same model
inspect eval my_env_task.py --model anthropic/claude-3-5-haiku-latest

# Agent 0 = Claude, agent 1 = GPT-4o-mini
inspect eval my_env_task.py --model anthropic/claude-3-5-haiku-latest \
    -T opponent_model=openai/gpt-4o-mini

# Human plays agent 0 in the terminal
inspect eval my_env_task.py@my_env_human_baseline \
    --model anthropic/claude-3-5-haiku-latest

# Human approves every action before it executes (LLM proposes, you approve)
inspect eval my_env_task.py --model anthropic/claude-3-5-haiku-latest \
    --approval human

# Open the results viewer
inspect view
```

---

## How It Works

Inspect evaluates a single "subject" model through a `Task → Dataset → Solver → Scorer` pipeline. The bridge maps Wordplay's concepts onto these primitives:

| Wordplay | Inspect |
|---|---|
| Environment instance | Lives inside a `@solver`, one per `Sample` |
| `env.step()` | Called by the solver after all agents have acted |
| Agent action selection | Model calls the `wordplay_action` tool with an integer index |
| `env.observe()` | Formatted into the user message preceding each tool call |
| `env.reset()` | Called at the start of `solve()`, seeded from `Sample.metadata` |
| Rewards / termination | Read by the `@scorer` from `WordplayEpisodeState` in the store |
| Full episode trajectory | Stored in `WordplayEpisodeState.trajectory` (accessible to scorer and log analysis) |

**Multi-agent:** Inspect is built around one subject model. The bridge approximates multi-agent by calling two separate `get_model()` instances inside the solver — one for agent 0 (the subject under evaluation) and one for all other agents (the opponent). Their turns are gathered concurrently via `asyncio.gather`, then `env.step()` is called with all actions at once, matching Wordplay's existing step contract exactly.

**Action selection:** The model is given a numbered list of possible actions and calls the `wordplay_action(action_index: int)` tool with an integer. This is robust to paraphrasing and avoids the fragility of string matching. If the model passes an out-of-range index, Inspect feeds the error back to the model for self-correction.

---

## Discussion-Phase Environments

Environments that extend `Discussion_Phase_With_Reset_Environment` are supported out of the box. Set `discussion_turns` to match your env's `discussion_phase_turn_count`:

```python
solver=wordplay_episode_solver(
    env_factory=make_env,
    discussion_turns=3,
)
```

During the discussion phase agents send plain text messages (no tool call). During the action phase they call `wordplay_action` as normal.

---

## Custom Scoring

The default scorer returns the **cumulative reward** for `agent_id` accumulated across all steps. Override with any `score_fn(env, agent_id, ep_state) -> float`:

```python
# Binary win/loss based on final cumulative reward
def win_loss(env, agent_id, ep):
    if len(ep.cumulative_rewards) < 2:
        return 0.0
    return 1.0 if ep.cumulative_rewards[0] > ep.cumulative_rewards[1] else 0.0

scorer=wordplay_outcome_scorer(agent_id=0, score_fn=win_loss)
```

`ep` is a `WordplayEpisodeState` with these fields:

| Field | Type | Description |
|---|---|---|
| `cumulative_rewards` | `list[float]` | Total reward per agent across the episode |
| `step_count` | `int` | Number of steps taken |
| `trajectory` | `list[dict]` | Per-step record of actions, rewards, terminations |
| `done` | `bool` | Whether the episode completed |

---

## Multiple Seeds / Parallel Episodes

Each `Sample` gets its own independent env instance via `env_factory()`, so parallel execution is safe. Inspect runs samples in parallel by default. Control concurrency with:

```bash
inspect eval my_env_task.py --model claude-3-5-haiku-latest --max-connections 4
```

---

## Head-to-Head Sweeps

To compare two models symmetrically, run twice with roles swapped and average the results:

```bash
# Model A as agent 0
inspect eval altar_inspect_task.py@altar_head_to_head \
    --model model_a -T opponent_model=model_b

# Model B as agent 0
inspect eval altar_inspect_task.py@altar_head_to_head \
    --model model_b -T opponent_model=model_a
```

Or use `eval_set` to run both configurations in one command:

```python
from inspect_ai import eval_set
eval_set([
    ("altar_inspect_task.py@altar_head_to_head", {"opponent_model": "openai/gpt-4o-mini"}),
], models=["anthropic/claude-3-5-haiku-latest"])
```

---

## Making Your Environment Work Well

**`__str__` on actions matters.** The model sees a numbered list of `str(action_sel)` values. Make sure each action's `action_description_text()` returns something short and unambiguous:

```python
class Move_North(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity):
        return "Move North"   # ✓ short and distinct
```

**Keep `env.properties.description` informative.** It's injected directly into the agent's system prompt, so it should tell the model what the game is and what it's trying to achieve.

---

## Known Limitations

| Limitation | Notes |
|---|---|
| One subject model per `inspect eval` invocation | Agent 1 is approximated by a second `get_model()` call, not a separate Inspect subject. Run twice with roles swapped for symmetric head-to-head results. |
| Synchronous env step | `env.step()` is called synchronously after all agents have acted. Truly real-time concurrent environments are not supported. |
| Training / RL loops | Not supported by Inspect by design. Use your existing `exp_exec.py` for training runs. |
| `env` is not JSON-serialisable | The live env object is stored with `exclude=True` in `WordplayEpisodeState`, so it won't appear in log files. Trajectory data is serialised instead. |