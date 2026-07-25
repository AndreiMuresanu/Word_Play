from __future__ import annotations

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
from word_play.presets.systems.preferences import Preference
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.coins.mechanics import CoinPatch
from benchmarks.text_mp.substrates.coins.variants import CoinsVariant


_COIN_PREFERENCES = [
    ("red_coin", "red"),
    ("blue_coin", "blue"),
]


def build_env(
    *,
    variant: CoinsVariant,
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

    entities = tilemap_to_entities(variant.tilemap.replace("P", "."), _tileset())
    spawn_positions = find_tile_positions(variant.tilemap, "P")
    total_agents = variant.default_agent_count if agent_count is None else agent_count
    if total_agents > len(spawn_positions):
        raise ValueError(f"Map only has {len(spawn_positions)} spawn positions.")

    for agent_id, (x, y) in enumerate(spawn_positions[:total_agents], start=1):
        preferred_tag, preferred_color = _COIN_PREFERENCES[agent_id - 1]
        entities.append(_build_agent(agent_id, x, y, preferred_tag, preferred_color, variant, policy_kind))

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.coins_events = []
    return env


def _tileset() -> dict:
    return {
        "W": {
            "name": "Wall",
            "tags": ["wall"],
            "components": [
                Collidable(collidable_tags=["wall"]),
            ],
        },
        "r": {
            "name": "Red Coin",
            "components": [
                CoinPatch("red"),
            ],
        },
        "b": {
            "name": "Blue Coin",
            "components": [
                CoinPatch("blue"),
            ],
        },
    }


def _build_agent(
    agent_id: int,
    x: int,
    y: int,
    preferred_tag: str,
    preferred_color: str,
    variant: CoinsVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=(
            f"You are Player {agent_id} in Coins. Your coin color is {preferred_color}. "
            f"{variant.prompt}"
        ),
        observation_memory_window=4,
        conversation_memory_window=8,
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
        ],
        components=[
            agent_policy,
            Preference(
                reward_map={preferred_tag: 1.0},
                default_reward=1.0,
                mismatch_penalty=-2.0,
            ),
            Collidable(collidable_tags=["wall"]),
        ],
    )
