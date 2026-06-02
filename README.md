# Word Play

# Beta Disclaimer

Word Play is currently in public beta. The framework is stable, however, we are still collecting feedback from the community and do not yet commit to long-term backwards compatability until the full release. Please let me us know if you run into any issues, we are happy to help.

# Quick Start
Word Play is a small framework for building text-first multi-agent environments.
It is designed around plain Python environment classes, composable entity
components, and readable observations that can be consumed by humans or LLM
policies.

## Quick Start

From the repo root:

```bash
pip install -e .
python examples/simple_env_0.py
```

Some examples use optional packages. Install them with:

```bash
pip install -r optional_requirements.txt
```

The LLM examples also require an OpenRouter API key:

```bash
export OPENROUTER_API_KEY=...
python examples/agent_goal_tracking.py
python examples/llm_communication.py
```

## Examples

- `examples/simple_env_0.py`: a minimal `Simple_2D_Grid_World` showing human-controlled actions, communication, combat, health, inventory, and collision.
- `examples/complex_tilemap.py`: a larger tilemap-driven grid world that demonstrates `tilemap_to_entities`, `randomize_agent_order`, observation radius, and typed action kwargs.
- `examples/rendering_demo.py`: a live pygame rendering demo with sprite-backed entities, walls, items, mixed human and random policies, and reset/quit handling through `env.render()`.
- `examples/parallelized_agents.py`: a renderer-backed arena that computes multiple agent actions in parallel. This is an important speed-up for multi-agent environments
- `examples/agent_goal_tracking.py`: a small one-dimensional action-only LLM example where an agent learns to move toward a goal under a time limit.
- `examples/llm_communication.py`: a three-agent LLM coordination game where each agent shares a private signal, communicates, and then chooses a synchronized action.

## Optional Dependencies

The base package intentionally has no runtime dependencies in `requirements.txt`.
Optional features need extra packages:

- Renderer presets: `pygame`
- OpenRouter-backed LLM models: `openai`

Install both with:

```bash
pip install -r optional_requirements.txt
```

## Design Philosophy

Word Play environments are meant to be easy to inspect and extend. The main
building blocks are:

- `Entity`: a named object in the environment with a position, tags, actions, and components.
- `Action`: executable behavior with validation rules and optional typed kwargs.
- `Component`: reusable state or behavior attached to an entity. Components can add tags, actions, and lifecycle hooks.
- `Agent_Policy`: a component that chooses an action from an observation.
- `Communication_Policy`: a component for message passing between agents.
- `Environment`: the simulation driver. It owns entities, movement, rewards, observations, and step execution.

The environment step follows an Agent Environment Cycle-style execution model:
agent actions are selected for the current step, then executed in the current
entity order. This matters when actions conflict. For example, if two agents try
to pick up the same item, the earlier entity in the execution order can succeed
and the later one can fail. See `src/word_play/core/environment.py` for the full
step sequence.

Entity order is configurable. Use `entity_definition_order` for deterministic
definition order, `random_order` to shuffle all entities, or
`randomize_agent_order` to shuffle only agents while preserving non-agent
placement. `randomize_agent_order` is useful when turn order could otherwise
create an unfair advantage.

## Building an Environment

A typical environment defines:

1. Entities, including each agent's actions and policy components.
2. A movement system that determines position type and nearby entities.
3. A reward function returning one reward per agent.
4. An `observe(agent_id)` method that returns an `Observation`.
5. Optional start/end-of-step logic for environment-specific state.

For many grid-world examples, start with `Simple_2D_Grid_World` and
`Simple_Observation`. Add custom sections to observations with
`extra_sections` when the agent needs task-specific context.

## Renderer

The renderer preset is a pygame renderer for watching an environment live,
inspecting agents, focusing an agent's observation window, and replaying a
saved run.

### Add Sprites To Entities

Attach `Renderable` to each entity you want to draw:

```python
from word_play.core import Entity
from word_play.presets.movement.simple_2d_grid import Position_2D
from word_play.presets.renderers import Renderable

player = Entity(
    name="Alice",
    position=Position_2D(2, 3),
    tags=["player"],
    components=[
        Renderable(
            sprite_path="sprite_library/src/characters/humanoids/dwarven/dwarf_expert.png",
            z_index=10,
        ),
    ],
)
```

For walls, pass `wall_set`; the renderer handles the wall connections and can
infer the floor area from the wall positions:

```python
wall = Entity(
    name="Wall",
    position=Position_2D(1, 1),
    tags=["wall"],
    components=[
        Renderable(
            sprite_path="sprite_library/src/world_tiles/indoors/wall_sets/bright_brick_wall/bright_brick_wall_center.png",
            wall_set="sprite_library/src/world_tiles/indoors/wall_sets/bright_brick_wall",
        ),
    ],
)
```

Set the floor sprite on the environment:

```python
env.floor_sprite = "sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png"
```

### Live Rendering

Call `render_step(env)` inside your normal experiment loop:

```python
from word_play.core import Agent_Policy
from word_play.presets.renderers import render_step

for step in range(100):
    if not render_step(env, step_delay=0.15):
        break

    selections = []
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        action_selection, _ = agent.get_component(Agent_Policy).select_action(observation)
        selections.append(action_selection)

    env.step(selections)
```

Live controls:

- Left click an agent to open the agent info card.
- Right click an agent to focus and follow its observation-sized view.
- Right click empty space to return to the full environment view.
- `R` calls `env.reset()` if the environment has a reset method.
- Escape or closing the window quits rendering.

When `Human_Takes_Action` or `Human_Communication_Policy` is used with a
rendered environment, action selection, action kwargs, and chat input appear in
the pygame sidebar instead of the terminal.

The sidebar shows the current observation, available actions, selected action,
and any required action input.

### Replays

Use `record_step` to save replay frames:

```python
from word_play.core import Agent_Policy
from word_play.presets.renderers import record_step

for step in range(100):
    selections = []
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        action_selection, _ = agent.get_component(Agent_Policy).select_action(observation)
        selections.append(action_selection)

    env.step(selections)
    record_step(env, title="my_renderer_run", selected_actions=selections)
```

Replay the saved experiment:

```python
from word_play.presets.renderers import replay

replay("path/to/experiment_log.pkl")
```

You can also run the replay CLI from the repo root:

```bash
PYTHONPATH=src python -m word_play.presets.renderers.renderer path/to/experiment_log.pkl
```

Replay controls:

- Space toggles autoplay.
- Right arrow, Enter, or keypad Enter advances one frame.
- Left arrow goes back one frame.
- Home jumps to the first frame.
- End jumps to the last frame.
- `R` restarts the replay from frame zero.
- Left click an agent to open the agent info card.
- Right click an agent to focus and follow its observation-sized view.
- Right click empty space to return to the full view.
- Escape or closing the window quits the replay.

## Presets Overview

The `src/word_play/presets` folder contains reusable pieces for common
environments:

- `action_policies`: human input, fixed action sequences, and LLM action plus communication policy.
- `models`: model interface, registry, human model, and OpenRouter model.
- `movement`: simple 1D grid, 2D grid, single-point movement, and collision helpers.
- `observation`: `Simple_Observation` plus formatting helpers for action lists and entity state.
- `systems`: reusable gameplay systems such as communication, combat, health, inventory, action composition, and do-nothing actions.
- `environments`: ready-made environment bases such as `Simple_2D_Grid_World`.
- `renderers`: pygame-based renderer/runtime tools.
- `entity_orderings.py`: deterministic and randomized entity ordering helpers.
- `reward_functions.py`: simple reward helpers.
- `action_args.py` and `action_validations.py`: reusable typed kwargs and action validators.

For renderer architecture, extension points, and pygame implementation details,
see `src/word_play/presets/renderers/README.md`.

## Codebase Layout

- `src/word_play/core`: framework primitives: actions, components, entities, environments, movement, and observations.
- `src/word_play/presets`: reusable policies, systems, movement models, observations, models, renderers, and environment helpers.
- `src/word_play/utils`: utility helpers, including tilemap construction.
- `examples`: small runnable examples showing how to assemble environments.
- `sprite_library`: renderer sprite assets and generation utilities.
- `tests`: test package placeholder.

## Acknowledgements

We acknowledge the following sponsors, who support our research with financial and in-kind contributions: CIFAR through the Canada CIFAR AI Chair, NSERC through the Discovery Grant and an Alliance Grant with ServiceNow and DRDC, the Schmidt Sciences foundation through the AI2050 Early Career Fellow program. Resources used in preparing this research were provided, in part, by the Province of Ontario, the Government of Canada through CIFAR, and companies sponsoring the Vector Institute. We thank the computing team at the University of Toronto’s Computer Science Department for administrating and procuring the compute infrastructure used for the experiments in this paper.

This work was supported in part by the German Federal Ministry of Education and Research (BMBF): Tübingen AI Center, FKZ: 01IS18039B; by the Machine Learning Cluster of Excellence, EXC number 2064/1 – Project number 390727645; by Schmidt Sciences SAFE-AI Grant; by the Frontier Model Forum and AI Safety Fund; by Coefficient Giving; by the Canadian AI Safety Institute Research Program at CIFAR; by the Canadian AI Safety Institute Research Program at CIFAR through a Catalyst Award; by the Survival and Flourishing Fund; and by the Cooperative AI Foundation. The usage of OpenAI credits is largely supported by the Tübingen AI Center and Schmidt Sciences. Resources used in preparing this research project were provided, in part, by the Province of Ontario, the Government of Canada through CIFAR, and companies sponsoring the Vector Institute.

We are thankful to Darci Prout for coming up with the name "WordPlay."
