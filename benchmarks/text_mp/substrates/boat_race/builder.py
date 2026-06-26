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
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.reward import Rewardable
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.boat_race.mechanics import BoatFood, Flail, Paddle
from benchmarks.text_mp.substrates.boat_race.variants import BoatRaceVariant


def build_env(
    *,
    variant: BoatRaceVariant,
    agent_count: int | None,
    policy_kind: PolicyKind,
    model_name: str,
    generation_config: dict | None = None,
) -> Simple_2D_Grid_World:
    if policy_kind == "llm":
        register_llm_model(
            variant.model_key,
            model_name=model_name,
            generation_config=generation_config,
        )

    entities = tilemap_to_entities(variant.tilemap, _tileset())
    spawn_positions = find_tile_positions(variant.tilemap, "_")
    random.shuffle(spawn_positions)
    total_agents = variant.default_agent_count if agent_count is None else agent_count
    if total_agents > len(spawn_positions):
        raise ValueError(f"Map only has {len(spawn_positions)} spawn positions.")

    for agent_id, (x, y) in enumerate(spawn_positions[:total_agents], start=1):
        entities.append(_build_agent(agent_id, x, y, variant, policy_kind))

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.boat_events = []
    env.boat_progress = 0
    env.boat_num_races = variant.race_count
    return env


def _tileset() -> dict:
    return {
        "W": {
            "name": "River Bank Wall",
            "tags": ["wall", "blocker"],
            "components": [
                Collidable(collidable_tags=["wall", "blocker"]),
            ],
        },
        "~": {
            "name": "Deep Water",
            "tags": ["water", "blocker"],
            "components": [
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "{": {
            "name": "Water",
            "tags": ["water"],
        },
        "g": {
            "name": "Goal Water",
            "tags": ["water", "goal"],
        },
        "S": {
            "name": "Semaphore Tile",
            "tags": ["floor"],
        },
        "B": {
            "name": "Barrier",
            "tags": ["barrier", "blocker"],
            "components": [
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "A": {
            "name": "Apple",
            "tags": ["apple", "food"],
            "components": [
                BoatFood(reward=1.0),
                Rewardable(amount=1.0),
            ],
        },
        "b": {
            "name": "Boat",
            "tags": ["boat"],
        },
        "o": {
            "name": "Oar",
            "tags": ["oar"],
        },
        "s": {
            "name": "Boat Seat",
            "tags": ["seat", "goal"],
        },
        "_": {
            "name": "Spawn Dock",
            "tags": ["spawn", "floor"],
        },
    }


def _build_agent(agent_id: int, x: int, y: int, variant: BoatRaceVariant, policy_kind: PolicyKind) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are Player {agent_id} in Boat Race: {variant.title}. {variant.prompt}",
        observation_memory_window=4,
        conversation_memory_window=4,
    )
    return Entity(
        name=f"Player {agent_id}",
        position=Position_2D(x, y),
        tags=["agent", "player", "default"],
        actions=[
            Do_Nothing(),
            Move_Up(),
            Move_Down(),
            Move_Left(),
            Move_Right(),
            Paddle(),
            Flail(),
        ],
        components=[
            agent_policy,
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
