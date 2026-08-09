from __future__ import annotations

from word_play.core import Entity, Environment
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
from word_play.presets.systems.containers.presets import Regrowable_Item_Source, Take_From_Infinite_Source
from word_play.presets.systems.crafter import Crafter, Crafter_Recipe, Load_First_Into_Crafter
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.inventory import Drop_Item, Inventory, Put_In_Container, Take_First_From_Container
from word_play.presets.systems.reward import Rewardable
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions

from benchmarks.text_mp.core.policies import PolicyKind, make_policy, register_llm_model
from benchmarks.text_mp.substrates.collaborative_cooking.mechanics import (
    COOKING_DELIVERY_REWARD,
    COOKING_TIME,
    Plate_Ready_Soup_With_Dish,
    collaborative_cooking_events,
)
from benchmarks.text_mp.substrates.collaborative_cooking.variants import CollaborativeCookingVariant


def _on_soup_delivered(actor: Entity, target: Entity, env: Environment, reward: float) -> None:
    collaborative_cooking_events(env).append(
        f"{actor.name} delivered soup (order #{env.completed_orders}) for +{reward:g} shared reward!"
    )


def build_env(
    *,
    variant: CollaborativeCookingVariant,
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

    entities = tilemap_to_entities(variant.tilemap.replace("P", "."), _tileset())
    spawn_positions = find_tile_positions(variant.tilemap, "P")
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
    env.completed_orders = 0
    env.collaborative_cooking_events = []
    return env


def _tileset() -> dict:
    tomato_factory = Entity(
        name="Tomato",
        position=Position_2D(0, 0),
        tags=["tomato", "ingredient"],
    )
    dish_factory = Entity(
        name="Dish",
        position=Position_2D(0, 0),
        tags=["dish"],
    )
    soup_output = Entity(
        name="Cooked Soup",
        position=Position_2D(0, 0),
        tags=["soup", "cooked_soup"],
    )
    return {
        "W": {
            "name": "Kitchen Wall",
            "tags": ["wall"],
            "components": [
                Collidable(collidable_tags=["wall"]),
            ],
        },
        "#": {
            "name": "Counter",
            "tags": ["counter", "blocker"],
            "components": [
                Inventory(max_size=1),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "O": {
            "name": "Tomato Source",
            "tags": ["tomato_source", "source", "blocker"],
            "components": [
                Regrowable_Item_Source(item_factory=tomato_factory, regen_rate=1),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "D": {
            "name": "Dish Source",
            "tags": ["dish_source", "source", "blocker"],
            "components": [
                Regrowable_Item_Source(item_factory=dish_factory, regen_rate=1),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "C": {
            "name": "Cooking Pot",
            "tags": ["pot", "blocker"],
            "components": [
                Crafter(
                    recipes=[
                        Crafter_Recipe(
                            input_names=("Tomato", "Tomato", "Tomato"),
                            output=soup_output,
                            duration=COOKING_TIME,
                        )
                    ]
                ),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
        "T": {
            "name": "Delivery Window",
            "tags": ["delivery", "blocker"],
            "components": [
                Rewardable(
                    amount=COOKING_DELIVERY_REWARD,
                    recipients="all",
                    counter_attr="completed_orders",
                    on_reward=_on_soup_delivered,
                ),
                Collidable(collidable_tags=["blocker"]),
            ],
        },
    }


def _build_agent(
    agent_id: int,
    x: int,
    y: int,
    variant: CollaborativeCookingVariant,
    policy_kind: PolicyKind,
) -> Entity:
    agent_policy = make_policy(
        policy_kind=policy_kind,
        model_key=variant.model_key,
        system_prompt=f"You are Player {agent_id} in Collaborative Cooking. {variant.prompt}",
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
            Drop_Item(),
            Take_From_Infinite_Source(),
            Load_First_Into_Crafter(),
            Plate_Ready_Soup_With_Dish(),
            Put_In_Container(["delivery"], ["soup"], destroy_item=True),
            Take_First_From_Container(target_tags=["counter"]),
            Put_In_Container(target_tags=["counter"], destroy_item=False),
        ],
        components=[
            agent_policy,
            Inventory(max_size=1, accepted_tags=["tomato", "dish", "soup", "ingredient"]),
            Collidable(collidable_tags=["wall", "blocker"]),
        ],
    )
