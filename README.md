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
python examples/llm_action_only_goal_line.py
python examples/llm_three_agent_communication.py
```

## Examples

- `examples/simple_env_0.py`: a hand-built `Simple_2D_Grid_World` with human action and communication policies, movement, combat, health, inventory, collision, and nearby entities.
- `examples/simple_env_1.py`: similar to `simple_env_0.py`, but builds entities from a compact tilemap and includes an action with typed kwargs.
- `examples/complex_tilemap.py`: a larger tilemap example using the list-based tilemap format and `randomize_agent_order`.
- `examples/llm_action_only_goal_line.py`: one LLM-controlled agent using `LLM_Action_And_Communication_Policy` for action selection only. No communication actions are added.
- `examples/llm_three_agent_communication.py`: three LLM-controlled agents share private signals, then choose actions based on the conversation. This is a compact check that LLM communication is working.

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

## Codebase Layout

- `src/word_play/core`: framework primitives: actions, components, entities, environments, movement, and observations.
- `src/word_play/presets`: reusable policies, systems, movement models, observations, models, renderers, and environment helpers.
- `src/word_play/utils`: utility helpers, including tilemap construction.
- `examples`: small runnable examples showing how to assemble environments.
- `sprite_library`: renderer sprite assets and generation utilities.
- `tests`: test package placeholder.

## Acknowledgements

We are thankful to Darci Prout for coming up with the name "WordPlay."
