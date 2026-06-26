from __future__ import annotations

import random

from word_play.core import Entity
from word_play.presets.action_validations import Target_Within_Range
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
from word_play.presets.systems.inventory import Inventory, Pick_Up_Item
from word_play.presets.systems.stamina import Has_Stamina, Stamina
from word_play.presets.systems.zap import Zap_Change
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.factory_commons.mechanics import (
    DepositFactoryCube,
    FactoryCube,
    FactoryHopper,
)
from benchmarks.text_mp.substrates.factory_commons.variants import FactoryCommonsVariant


def build_env(
    *,
    variant: FactoryCommonsVariant,
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
    spawn_positions = _spawn_positions(variant.tilemap)
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
    env.factory_events = []
    return env


def _tileset() -> dict:
    return {
        "W": {
            "name": "Wall",
            "tags": ["wall", "blocker"],
            "components": [
                Collidable(collidable_tags=["wall", "blocker"]),
            ],
        },
        "c": {
            "name": "Waiting Cube",
            "components": [
                FactoryCube(live=False),
            ],
        },
        "C": {
            "name": "Cube",
            "components": [
                FactoryCube(live=True),
            ],
        },
        "H": {
            "name": "Double Hopper",
            "tags": ["blocker"],
            "components": [
                FactoryHopper(output_count=2),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "h": {
            "name": "Single Hopper",
            "tags": ["blocker"],
            "components": [
                FactoryHopper(output_count=1),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "O": {
            "name": "Output Belt",
            "tags": ["belt"],
        },
    }


def _spawn_positions(tilemap: str) -> list[tuple[int, int]]:
    central_spawns = [(12, 5), (11, 5), (13, 5)]
    spawn_positions = [
        *central_spawns,
        *[position for position in find_tile_positions(tilemap, ".") if position not in set(central_spawns)],
    ]
    random.shuffle(spawn_positions)
    return spawn_positions


def _build_agent(
    agent_id: int,
    x: int,
    y: int,
    variant: FactoryCommonsVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are Player {agent_id} in Factory Commons: {variant.title}. {variant.prompt}",
        observation_memory_window=1,
        conversation_memory_window=1,
    )
    return Entity(
        name=f"Player {agent_id}",
        position=Position_2D(x, y),
        tags=["agent", "player", "default"],
        actions=[
            Do_Nothing(),
            Move_Up(Has_Stamina("move")),
            Move_Down(Has_Stamina("move")),
            Move_Left(Has_Stamina("move")),
            Move_Right(Has_Stamina("move")),
            Pick_Up_Item(["cube"]),
            DepositFactoryCube(),
            Zap_Change(
                allowed_tag="apple",
                target_is_nearby=Target_Within_Range(2).is_valid,
                reward=1.0,
                action_name="Eat",
            ),
        ],
        components=[
            agent_policy,
            Inventory(max_size=1, accepted_tags=["cube"]),
            Stamina(maximum=10, action_costs={"move": 1}),
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
