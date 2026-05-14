# Word Play Environment Prompt

Use this prompt when creating a new Word Play environment file.

## Goal

Create the environment in the same style as [examples/simple_env_1.py](/Users/iamsogoodlo/Documents/Projects/Word_Play_MP/examples/simple_env_1.py):

- keep everything in one file
- define the map as an inline `entity_tilemap` string
- define the entities as an inline `entity_tileset` dictionary
- use `Simple_2D_Grid_World`
- use presets wherever possible instead of reinventing systems
- keep the main entrypoint as a `run_exp()` loop that directly steps the env

## Look At Presets.md

Before creating the environment, read [presets.md](/Users/iamsogoodlo/Documents/Projects/Word_Play_MP/presets.md).

Use it to:

- see which preset systems already exist
- prefer preset actions/components over new custom code
- avoid rebuilding mechanics that are already available
- check the names of the exact preset modules, classes, and helper functions

Default rule:

- if a mechanic can be expressed with a preset, use the preset
- only write custom actions or components for the parts that are truly environment-specific

## Required Shape

Follow this structure closely:

```python
from word_play.core import (
    Action,
    Agent_Policy,
    Entity,
    Target_Is_Self,
)
from word_play.presets.action_args import ...
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.entity_orderings import randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import ...
from word_play.presets.systems... import ...
from word_play.utils import tilemap_to_entities


class Custom_Action(Action):
    ...


def run_exp():
    exp_steps = 1000

    entity_tilemap = \"\"\"
    ...
    \"\"\"

    entity_tileset = {
        ...
    }

    env = Simple_2D_Grid_World(
        description="...",
        entities=tilemap_to_entities(entity_tilemap, entity_tileset),
        entity_order=randomize_agent_order,
        observation_radius=...,
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp()
```

## Tilemap Rules

Define the environment layout exactly like this:

```python
entity_tilemap = """
WWWWWWWWW
W..a...bW
W.A...B.W
W..c....W
WWWWWWWWW
"""
```

Use one character per tile.

- `.` means empty floor
- each other character maps to one entry in `entity_tileset`
- walls, items, NPCs, players, hazards, and stations should all be represented in the tilemap

Do not build the map with coordinate lists unless absolutely necessary. Prefer the inline ASCII tilemap.

## Tileset Rules

Define the mapping inline right below `entity_tilemap`:

```python
entity_tileset = {
    "W": {
        "name": "Wall",
        "tags": ["wall"],
        "components": [Collidable()],
    },
    "A": {
        "name": "Player One",
        "actions": [
            Do_Nothing(),
            Move_Up(),
            Move_Down(),
            Move_Left(),
            Move_Right(),
        ],
        "components": [
            Human_Takes_Action(),
            Collidable(collidable_tags=["wall"]),
        ],
    },
    "a": {
        "name": "Apple",
        "tags": ["item"],
    },
}
```

Every non-empty tile character used in `entity_tilemap` must appear in `entity_tileset`.

If a tile or entity uses a `Renderable`, define the `sprite_path` inline inside the `Renderable(...)` component.

- do not create sprite path helper functions
- do not alias sprite paths through constants unless there is a very strong reason
- prefer the literal asset path directly in each `Renderable(...)`

## Preset Preference

Prefer existing presets before writing custom logic.

Useful presets:

- movement: `Move_Up`, `Move_Down`, `Move_Left`, `Move_Right`, `Collidable`, `Position_2D`
- no-op: `Do_Nothing`
- combat: `Attack`
- health: `Health`
- inventory: `Inventory`, `Pick_Up_Item`, `Drop_Item`, `Put_In_Container`
- reward and preference: `Rewardable`, `Preference`
- freeze/zap/cooldowns: `Freezable`, `Freeze`, `Cooldown`, `ZapMarking`, `Zap_Player`, `Zap_Change`
- communication: `Start_Public_Conversation`, `Start_Private_Conversation`, `Human_Communication_Policy`, `TalkingCow`
- automation for NPCs: `Follow_Action_Sequence`

Only add a custom `Action` or `Component` when the desired behavior does not already exist in the preset library.

## Agent Setup

For agent entities, prefer this pattern:

```python
"A": {
    "name": "Agent Name",
    "actions": [
        Do_Nothing(),
        Move_Up(),
        Move_Down(),
        Move_Left(),
        Move_Right(),
        Attack(name="Zap", damage_amount=1),
    ],
    "components": [
        Human_Takes_Action(),
        Inventory(
            collectable_tags=["item"],
            inventory_size=2,
        ),
        Health(max_health=5, starting_health=5),
        Collidable(collidable_tags=["wall"]),
    ],
}
```

For scripted NPCs, prefer:

```python
"c": {
    "name": "Cow",
    "actions": [Move_Up(), Move_Down()],
    "components": [
        Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
        TalkingCow(),
    ],
}
```

## Environment Construction

Build the environment directly from the tilemap:

```python
env = Simple_2D_Grid_World(
    description="Short description here.",
    entities=tilemap_to_entities(entity_tilemap, entity_tileset),
    entity_order=randomize_agent_order,
    observation_radius=1,
)
```

Keep setup local to `run_exp()` unless there is a strong reason to factor helpers out.

## Run Loop

Use the plain explicit action-selection loop from `simple_env_1.py`:

```python
for step in range(exp_steps):
    cur_step_actions = []
    for agent_id, agent in enumerate(env.agents):
        observation = env.observe(agent_id)
        action, info = agent.get_component(Agent_Policy).select_action(observation)
        print(f"[step {step}] {agent.name} -> {action}")
        cur_step_actions.append(action)

    env.step(cur_step_actions)
```

This is the default expected format unless a benchmark file explicitly needs a different runner.

## Style Notes

- Keep the file readable and compact.
- Put the tilemap in the file, not in a separate asset.
- Define `Renderable(sprite_path="...")` asset paths inline where the component is declared.
- Put the tileset in the file, not in a separate config.
- Keep imports explicit.
- Avoid aliasing imports.
- Avoid custom environment subclasses unless `Simple_2D_Grid_World` truly cannot support the behavior.
- If custom actions are needed, define them above `run_exp()`.
- If custom components are needed, define them above `run_exp()`.

## Output Request Template

When asked to build a new environment, follow this instruction:

> Create a single-file Word Play environment in the same format as `examples/simple_env_1.py`. Use an inline ASCII `entity_tilemap`, an inline `entity_tileset`, `Simple_2D_Grid_World`, and as many existing presets as possible. Only add custom actions/components where necessary. End with a `run_exp()` function and `if __name__ == "__main__": run_exp()`.
