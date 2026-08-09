from __future__ import annotations

from word_play.core import Entity
from word_play.presets.entity_orderings import randomize_agent_order
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
from benchmarks.text_mp.substrates.hidden_agenda.mechanics import (
    FreezeCrewmate,
    GemDeposit,
    GemPatch,
    HiddenAgendaManager,
    HiddenAgendaState,
    HiddenAgendaWorld,
    VotingSpawn,
)
from benchmarks.text_mp.substrates.hidden_agenda.variants import (
    MANDATED_NUM_PLAYERS,
    HiddenAgendaVariant,
)


_ROLES = ["crewmate", "crewmate", "crewmate", "crewmate", "impostor"]


def build_env(
    *,
    variant: HiddenAgendaVariant,
    agent_count: int | None,
    policy_kind: PolicyKind,
    model_name: str,
    generation_config: dict | None = None,
) -> HiddenAgendaWorld:
    total_agents = variant.default_agent_count if agent_count is None else agent_count
    assert total_agents == MANDATED_NUM_PLAYERS, (
        f"Hidden Agenda requires exactly {MANDATED_NUM_PLAYERS} players."
    )

    if policy_kind == "llm":
        register_llm_model(
            variant.model_key,
            model_name=model_name,
            generation_config=generation_config or {"temperature": 0.3},
        )

    tileset = _tileset()
    entity_map = variant.tilemap.replace("P", ".")
    entities = tilemap_to_entities(entity_map, tileset)

    spawn_positions = find_tile_positions(variant.tilemap, "P")
    voting_positions = find_tile_positions(variant.tilemap, "V")

    assert len(spawn_positions) >= total_agents, (
        f"Map has only {len(spawn_positions)} spawn positions for {total_agents} agents."
    )

    entities.append(
        Entity(
            name="Hidden Agenda Manager",
            position=Position_2D(-1, -1),
            components=[HiddenAgendaManager(voting_positions=voting_positions)],
        )
    )

    for agent_id, ((x, y), role) in enumerate(
        zip(spawn_positions[:total_agents], _ROLES), start=1
    ):
        entities.append(_build_agent(agent_id, role, x, y, variant, policy_kind))

    env = HiddenAgendaWorld(
        description=variant.description,
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=variant.observation_radius,
    )
    env.hidden_agenda_events = []
    return env


def _tileset() -> dict:
    return {
        "W": {
            "name": "Ship Wall",
            "tags": ["wall", "blocker"],
            "components": [Collidable(collidable_tags=["wall", "blocker"])],
        },
        "G": {
            "name": "Gem",
            "tags": ["gem"],
            "components": [GemPatch()],
        },
        "O": {
            "name": "Gem Deposit",
            "tags": ["gem_deposit"],
            "components": [GemDeposit()],
        },
        "V": {
            "name": "Voting Spawn",
            "tags": ["voting_spawn"],
            "components": [VotingSpawn()],
        },
    }


def _build_agent(
    agent_id: int,
    role: str,
    x: int,
    y: int,
    variant: HiddenAgendaVariant,
    policy_kind: PolicyKind,
) -> Entity:
    spawn = Position_2D(x, y)
    if role == "impostor":
        system_prompt = (
            f"You are Player {agent_id} in Hidden Agenda: {variant.title}. "
            "You are the IMPOSTOR. Freeze crewmates when they are in range, "
            "survive deliberations, and prevent gem deposits. "
            f"{variant.prompt}"
        )
    else:
        system_prompt = (
            f"You are Player {agent_id} in Hidden Agenda: {variant.title}. "
            "You are a CREWMATE. Collect gems and deposit them. "
            "Vote for the impostor during deliberations. "
            f"{variant.prompt}"
        )
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=system_prompt,
        observation_memory_window=1,
        conversation_memory_window=1,
    )
    return Entity(
        name=f"Player {agent_id}",
        position=spawn,
        tags=["agent", "player", "default"],
        actions=[
            Do_Nothing(),
            Move_Up(),
            Move_Down(),
            Move_Left(),
            Move_Right(),
            FreezeCrewmate(),
        ],
        components=[
            agent_policy,
            HiddenAgendaState(role, spawn),
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
