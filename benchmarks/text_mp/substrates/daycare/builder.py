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
from word_play.presets.systems.inventory import Inventory
from word_play.presets.systems.respawnable import Respawnable
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.daycare.mechanics import (
    AvatarState,
    Eating,
    FRAMES_TILL_RESPAWN,
    FruitPatch,
    Grasp,
)
from benchmarks.text_mp.substrates.daycare.variants import DaycareVariant

_ROLES = ["child", "parent"]


def build_env(
    *,
    variant: DaycareVariant,
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
    assert total_agents == 2, "Daycare requires exactly 2 agents (child and parent)."

    entities = tilemap_to_entities(variant.tilemap.replace("P", "."), _tileset())
    spawn_positions = find_tile_positions(variant.tilemap, "P")

    for agent_id, role in enumerate(_ROLES, start=1):
        x, y = spawn_positions[agent_id - 1]
        entities.append(_build_agent(agent_id, role, x, y, variant, policy_kind))

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.daycare_events = []
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
        "F": {
            "name": "Fruit Patch",
            "tags": ["fruit_patch"],
            "components": [
                FruitPatch(),
            ],
        },
    }


def _build_agent(
    agent_id: int,
    role: str,
    x: int,
    y: int,
    variant: DaycareVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are the {role} in Daycare. {variant.prompt}",
        observation_memory_window=4,
        conversation_memory_window=8,
    )
    return Entity(
        name=role.title(),
        position=Position_2D(x, y),
        tags=["agent", "player", role],
        actions=[
            Do_Nothing(),
            Move_Up(),
            Move_Down(),
            Move_Left(),
            Move_Right(),
            Grasp(),
        ],
        components=[
            agent_policy,
            Respawnable(
                FRAMES_TILL_RESPAWN,
                respawn_position=Position_2D(x, y),
                inactive_position=Position_2D(-1000, -1000),
            ),
            AvatarState(role=role),
            Eating(),
            Inventory(accepted_tags=["fruit"], max_size=1),
            Collidable(collidable_tags=["wall"]),
        ],
    )
