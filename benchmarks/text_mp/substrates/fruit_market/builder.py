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
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.fruit_market.mechanics import (
    MAX_OFFER_QUANTITY,
    CancelTradeOffer,
    EatFruit,
    FruitInventory,
    FruitMarketAvatar,
    FruitMarketManager,
    FruitTree,
    SetTradeOffer,
    ShovePlayer,
    WaterCost,
)
from benchmarks.text_mp.substrates.fruit_market.variants import FruitMarketVariant


def build_env(
    *,
    variant: FruitMarketVariant,
    agent_count: int | None,
    policy_kind: PolicyKind,
    model_name: str,
    generation_config: dict | None = None,
) -> Simple_2D_Grid_World:
    if policy_kind == "llm":
        register_llm_model(
            variant.model_key,
            model_name=model_name,
            generation_config=generation_config or {"temperature": 0.3},
        )

    total_agents = variant.default_agent_count if agent_count is None else agent_count

    tileset = _tileset()
    entity_map = variant.tilemap
    for ch in "Pab":
        entity_map = entity_map.replace(ch, ".")
    # replace seeded apple/banana tree chars in tileset version
    # (they are handled separately below)
    entities = tilemap_to_entities(entity_map, tileset)

    # Seeded trees: parse positions from the original tilemap
    apple_positions = find_tile_positions(variant.tilemap, "a")
    banana_positions = find_tile_positions(variant.tilemap, "b")
    for x, y in apple_positions:
        entities.append(
            Entity(
                name="Apple Tree with fruit",
                position=Position_2D(x, y),
                tags=["tree_site"],
                components=[FruitTree("apple")],
            )
        )
    for x, y in banana_positions:
        entities.append(
            Entity(
                name="Banana Tree with fruit",
                position=Position_2D(x, y),
                tags=["tree_site"],
                components=[FruitTree("banana")],
            )
        )

    spawn_positions = find_tile_positions(variant.tilemap, "P")
    random.shuffle(spawn_positions)
    if total_agents > len(spawn_positions):
        raise ValueError(
            f"Map only has {len(spawn_positions)} spawn positions for {total_agents} agents."
        )

    entities.append(
        Entity(
            name="Fruit Market Manager",
            position=Position_2D(-1, -1),
            components=[FruitMarketManager()],
        )
    )

    for agent_id, (x, y) in enumerate(spawn_positions[:total_agents], start=1):
        specialty = "banana" if agent_id % 2 == 1 else "apple"
        entities.append(_build_agent(agent_id, specialty, x, y, variant, policy_kind))

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.fruit_market_events = []
    return env


def _tileset() -> dict:
    return {
        "W": {
            "name": "Wall",
            "tags": ["wall", "blocker"],
            "components": [Collidable(collidable_tags=["wall", "blocker"])],
        },
        "t": {
            "name": "Potential Fruit Tree",
            "tags": ["tree_site"],
            "components": [FruitTree()],
        },
        "R": {
            "name": "River",
            "tags": [],
            "components": [WaterCost()],
        },
    }


def _build_agent(
    agent_id: int,
    specialty: str,
    x: int,
    y: int,
    variant: FruitMarketVariant,
    policy_kind: PolicyKind,
) -> Entity:
    favorite = "banana" if specialty == "apple" else "apple"
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=(
            f"You are Player {agent_id} in Fruit Market: {variant.title}. "
            f"You are a {specialty} farmer: you harvest {specialty}s reliably, "
            f"but your favorite food is {favorite} (worth 8 reward). "
            f"{variant.prompt}"
        ),
        observation_memory_window=4,
        conversation_memory_window=8,
    )
    actions = [
        Do_Nothing(),
        Move_Up(),
        Move_Down(),
        Move_Left(),
        Move_Right(),
        EatFruit("apple"),
        EatFruit("banana"),
        CancelTradeOffer(),
        ShovePlayer(1),
        ShovePlayer(-1),
        *[
            SetTradeOffer(give_fruit, give_amount, want_amount)
            for give_fruit in ("apple", "banana")
            for give_amount in range(1, MAX_OFFER_QUANTITY + 1)
            for want_amount in range(1, MAX_OFFER_QUANTITY + 1)
        ],
    ]
    return Entity(
        name=f"Player {agent_id}",
        position=Position_2D(x, y),
        tags=["agent", "player", "default"],
        actions=actions,
        components=[
            agent_policy,
            FruitInventory(),
            FruitMarketAvatar(specialty),
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
