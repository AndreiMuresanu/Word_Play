from __future__ import annotations

import random

from word_play.core import Entity
from word_play.presets.entity_orderings import randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import (
    Collidable,
    Move_Down,
    Move_Left,
    Move_Right,
    Move_Up,
    Position_2D,
)
from word_play.presets.systems.cooldown import Cooldown
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.freezable import Freezable
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import Inventory
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.paintball.mechanics import (
    CTF_CAPTURE_REWARD,
    Flag,
    GrabFlag,
    HillZone,
    PaintballManager,
    PaintballZap,
    ZAP_COOLDOWN,
    ZAP_FREEZE_DURATION,
)
from benchmarks.text_mp.substrates.paintball.variants import PaintballVariant


def build_env(
    *,
    variant: PaintballVariant,
    agent_count: int | None,
    policy_kind: PolicyKind,
    model_name: str,
    generation_config: dict | None = None,
) -> Simple_2D_Grid_World:
    if policy_kind == "llm":
        register_llm_model(
            variant.model_key,
            model_name=model_name,
            generation_config=generation_config or {"temperature": 0.25},
        )

    total_agents = variant.default_agent_count if agent_count is None else agent_count

    tilemap = variant.tilemap
    if variant.mode == "ctf":
        tileset = _tileset_ctf()
        clean_chars = "PQ,I"
        red_base = find_tile_positions(tilemap, "F")[0]
        blue_base = find_tile_positions(tilemap, "G")[0]
    else:
        tileset = _tileset_hill()
        clean_chars = "PQ,Iurdl"
        red_base = None
        blue_base = None

    entity_map = tilemap
    for ch in clean_chars:
        entity_map = entity_map.replace(ch, ".")

    entities = tilemap_to_entities(entity_map, tileset)

    red_spawns = find_tile_positions(tilemap, "P")
    blue_spawns = find_tile_positions(tilemap, "Q")
    random.shuffle(red_spawns)
    random.shuffle(blue_spawns)
    if total_agents > len(red_spawns) + len(blue_spawns):
        raise ValueError(f"Map only has {len(red_spawns) + len(blue_spawns)} spawn positions.")
    red_count = min(len(red_spawns), (total_agents + 1) // 2)
    blue_count = total_agents - red_count
    spawn_assignments = (
        [("red", pos) for pos in red_spawns[:red_count]]
        + [("blue", pos) for pos in blue_spawns[:blue_count]]
    )

    for agent_id, (team, (x, y)) in enumerate(spawn_assignments, start=1):
        entities.append(_build_agent(agent_id, team, x, y, variant, policy_kind))

    entities.append(
        Entity(
            name="Paintball Manager",
            position=Position_2D(-1, -1),
            components=[PaintballManager(mode=variant.mode, red_base=red_base, blue_base=blue_base)],
        )
    )

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.paintball_events = []
    return env


def _tileset_ctf() -> dict:
    return {
        "W": {
            "name": "Wall",
            "tags": ["wall", "blocker"],
            "components": [Collidable(collidable_tags=["wall", "blocker"])],
        },
        "X": {
            "name": "Destructible Wall",
            "tags": ["wall", "blocker", "destructible"],
            "components": [
                Health(max_health=1),
                Collidable(collidable_tags=["wall", "blocker"]),
            ],
        },
        "F": {
            "name": "Red Flag",
            "tags": [],
            "components": [Flag("red")],
        },
        "G": {
            "name": "Blue Flag",
            "tags": [],
            "components": [Flag("blue")],
        },
    }


def _tileset_hill() -> dict:
    return {
        "W": {
            "name": "Wall",
            "tags": ["wall", "blocker"],
            "components": [Collidable(collidable_tags=["wall", "blocker"])],
        },
        "X": {
            "name": "Destructible Wall",
            "tags": ["wall", "blocker", "destructible"],
            "components": [
                Health(max_health=1),
                Collidable(collidable_tags=["wall", "blocker"]),
            ],
        },
        "G": {
            "name": "Hill",
            "tags": [],
            "components": [HillZone()],
        },
    }


def _build_agent(
    agent_id: int,
    team: str,
    x: int,
    y: int,
    variant: PaintballVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are Player {agent_id} on the {team} team in Paintball {variant.title}. {variant.prompt}",
        observation_memory_window=1,
        conversation_memory_window=1,
    )
    actions = [
        Do_Nothing(),
        Move_Up(),
        Move_Down(),
        Move_Left(),
        Move_Right(),
        PaintballZap(),
    ]
    components = [
        agent_policy,
        Cooldown(cooldowns={"paintball": ZAP_COOLDOWN}),
        Freezable(default_duration=ZAP_FREEZE_DURATION),
        Health(max_health=3, starting_health=2),
        Collidable(collidable_tags=["wall", "blocker"]),
    ]
    if variant.mode == "ctf":
        actions.append(GrabFlag())
        components.insert(1, Inventory(max_size=1, accepted_tags=["flag"]))

    return Entity(
        name=f"{team.title()} Player {agent_id}",
        position=Position_2D(x, y),
        tags=["agent", "player", "default", team],
        actions=actions,
        components=components,
    )
