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
from word_play.presets.systems.respawnable import Respawnable
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.predator_prey.mechanics import (
    ActorCanMove,
    CatchPrey,
    PredatorPreyFood,
    PredatorPreyRole,
)
from benchmarks.text_mp.substrates.predator_prey.variants import PredatorPreyVariant


def build_env(
    *,
    variant: PredatorPreyVariant,
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

    entities = tilemap_to_entities(
        variant.tilemap.replace("P", ".").replace("q", "."),
        _tileset(),
    )
    total_agents = variant.default_agent_count if agent_count is None else agent_count
    spawn_assignments = _spawn_assignments(variant, total_agents)

    for agent_id, (role, (x, y)) in enumerate(spawn_assignments, start=1):
        entities.append(_build_agent(agent_id, role, x, y, variant, policy_kind))

    env = Simple_2D_Grid_World(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.predator_prey_events = []
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
        "G": {
            "name": "Tall Grass",
            "tags": ["grass"],
            "components": [
                Collidable(collidable_tags=["predator"]),
            ],
        },
        "A": {
            "name": "Apple",
            "components": [
                PredatorPreyFood("apple", reward=1.0),
            ],
        },
        "C": {
            "name": "Acorn",
            "components": [
                PredatorPreyFood("acorn", reward=18.0),
            ],
        },
    }


def _spawn_assignments(variant: PredatorPreyVariant, agent_count: int) -> list[tuple[str, tuple[int, int]]]:
    predator_spawns = find_tile_positions(variant.tilemap, "P")
    prey_spawns = find_tile_positions(variant.tilemap, "q")
    open_spawns = find_tile_positions(variant.tilemap, ".")
    random.shuffle(predator_spawns)
    random.shuffle(prey_spawns)
    random.shuffle(open_spawns)

    predator_count = min(variant.default_predator_count, agent_count, len(predator_spawns))
    prey_count = agent_count - predator_count
    if prey_count > len(prey_spawns) + len(open_spawns):
        raise ValueError("Map does not have enough spawn positions.")

    assignments = [("predator", pos) for pos in predator_spawns[:predator_count]]
    assignments.extend(("prey", pos) for pos in (prey_spawns + open_spawns)[:prey_count])
    return assignments


def _build_agent(
    agent_id: int,
    role: str,
    x: int,
    y: int,
    variant: PredatorPreyVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are Player {agent_id}, a {role}, in Predator Prey: {variant.title}. {variant.prompt}",
        observation_memory_window=4,
        conversation_memory_window=4,
    )
    return Entity(
        name=f"{role.title()} {agent_id}",
        position=Position_2D(x, y),
        tags=["agent", "player", "default"],
        actions=[
            Do_Nothing(),
            Move_Up(ActorCanMove()),
            Move_Down(ActorCanMove()),
            Move_Left(ActorCanMove()),
            Move_Right(ActorCanMove()),
            CatchPrey(),
        ],
        components=[
            agent_policy,
            Respawnable(respawn_position=Position_2D(x, y), inactive_position=Position_2D(-1000, -1000)),
            PredatorPreyRole(role),
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
