from __future__ import annotations

from typing import TYPE_CHECKING

from word_play.core import (
    Action_Selection,
    Entity,
    Environment,
)
from word_play.presets.entity_orderings import entity_definition_order
from word_play.presets.environments.simple_env_reset_mixin import Simple_Env_Reset_Mixin
from word_play.presets.movement import Move_Down, Move_Left, Move_Right, Move_Up
from word_play.presets.movement.common import Collidable
from word_play.presets.movement.simple_2d_grid import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D
from word_play.presets.observation import Simple_Observation
from word_play.presets.renderers import Renderable
from word_play.presets.systems.communication import Start_Public_Conversation
from word_play.presets.systems import (
    Crafter,
    Crafter_Recipe,
    Deliver_Item,
    Dispense_From_Infinite_Source,
    Do_Nothing,
    Front_Order_Match,
    Infinite_Item_Source,
    Inventory,
    Load_Crafter,
    Named_Item_Reward,
    Pick_Up_Item,
    Put_In_Container,
    Record_Delivery,
    Single_Item_Holder,
)

if TYPE_CHECKING:
    from word_play.presets.renderers import Renderer


ASCII_KITCHEN = """
#############
#     #     #
# F   u   D #
#     #     #
# A C # S E #
#     #     #
# T   l   P #
#   N # L W #
#############
"""

OVERCOOKED_WALL_SET = "src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall"


def team_reward(action_selections: list[Action_Selection], env: Environment) -> list[float]:
    assert isinstance(env, OvercookedKitchenEnv)
    return [float(env.step_score_delta) for _ in env.agents]


def build_delivery_message(actor, target, env, item, reward) -> str:
    return f"{actor.name} served {item.name.replace('_', ' ')}."


class OvercookedKitchenEnv(Simple_Env_Reset_Mixin, Environment):
    AGENT_ACTIONS = [
        Move_Left(),
        Move_Right(),
        Move_Up(),
        Move_Down(),
        Start_Public_Conversation(),
        Pick_Up_Item(["collectable"]),
        Dispense_From_Infinite_Source(),
        Put_In_Container(),
        Load_Crafter(),
        Deliver_Item(
            target_tags=["serve"],
            item_is_valid=Front_Order_Match(),
            reward_for_item=Named_Item_Reward({"garden_skillet": 24.0}, default_reward=10.0),
            on_delivered=Record_Delivery(
                score_attr="score",
                step_score_attr="step_score_delta",
                count_attr="deliveries",
                order_attr="order_queue",
                log_attr="event_log",
                log_limit=8,
                message_builder=build_delivery_message,
            ),
        ),
        Do_Nothing(),
    ]

    def __init__(self, renderer: Renderer | None = None, episode_length: int = 60):
        self.renderer_impl = renderer
        self.episode_length = episode_length
        self.width = 13
        self.height = 9
        self.wall_set = OVERCOOKED_WALL_SET
        self.tick = 0
        self.score = 0
        self.deliveries = 0
        self.step_score_delta = 0
        self.sight_radius = 4
        self.order_queue = ["garden_skillet", "garden_skillet"]
        self.event_log = ["Cook two garden skillets and serve them."]
        tomato_counter = Entity(
            name="Tomato Counter",
            position=Position_2D(1, 6),
            tags=["blocker", "station", "source"],
            components=[
                Infinite_Item_Source(
                    Entity(
                        name="tomato",
                        position=Position_2D(0, 0),
                        tags=["collectable", "ingredient", "raw_food"],
                        components=[Renderable(sprite_path="src/items/consumables/vegetables/tomato_2.png", z_index=2)],
                    )
                ),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_7.png",
                    z_index=4,
                    overlay_sprite="src/items/consumables/vegetables/tomato_2.png",
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        protein_fridge = Entity(
            name="Protein Fridge",
            position=Position_2D(1, 2),
            tags=["blocker", "station", "source"],
            components=[
                Infinite_Item_Source(
                    Entity(
                        name="protein",
                        position=Position_2D(0, 0),
                        tags=["collectable", "ingredient", "raw_food"],
                        components=[Renderable(sprite_path="src/items/consumables/meat/steak_2.png", z_index=2)],
                    )
                ),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/fridge.png",
                    z_index=4,
                    overlay_sprite="src/items/consumables/meat/steak_2.png",
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        plate_stack = Entity(
            name="Plate Stack",
            position=Position_2D(9, 6),
            tags=["blocker", "station", "source"],
            components=[
                Infinite_Item_Source(
                    Entity(
                        name="plate",
                        position=Position_2D(0, 0),
                        tags=["collectable", "plate"],
                        components=[Renderable(sprite_path="src/items/equipment/armor/mirror_plate.png", z_index=2)],
                    )
                ),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_7.png",
                    z_index=4,
                    overlay_sprite="src/items/equipment/armor/mirror_plate.png",
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        chopping_board = Entity(
            name="Chopping Board",
            position=Position_2D(3, 4),
            tags=["blocker", "station", "crafter"],
            components=[
                Crafter(
                    recipes=[
                        Crafter_Recipe(
                            ("tomato",),
                            Entity(
                                name="chopped_tomato",
                                position=Position_2D(0, 0),
                                tags=["collectable", "ingredient", "prepared_food"],
                                components=[Renderable(sprite_path="src/items/consumables/vegetables/tomato_2.png", z_index=2)],
                            ),
                        ),
                        Crafter_Recipe(
                            ("protein",),
                            Entity(
                                name="chopped_protein",
                                position=Position_2D(0, 0),
                                tags=["collectable", "ingredient", "prepared_food"],
                                components=[Renderable(sprite_path="src/items/consumables/meat/steak_2.png", z_index=2)],
                            ),
                        ),
                    ]
                ),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_6.png",
                    z_index=4,
                    overlay_sprite="src/items/materials/misc/board_c.png",
                    overlay_mode="center",
                    overlay_scale=0.56,
                ),
            ],
        )
        stove = Entity(
            name="Stove",
            position=Position_2D(7, 4),
            tags=["blocker", "station", "crafter", "stove"],
            components=[
                Crafter(
                    recipes=[
                        Crafter_Recipe(
                            input_names=("chopped_tomato", "chopped_protein"),
                            output=Entity(
                                name="garden_skillet",
                                position=Position_2D(0, 0),
                                tags=["collectable", "dish", "prepared_food"],
                                components=[Renderable(sprite_path="src/items/materials/misc/dairy_pot.png", z_index=2)],
                            ),
                            duration=2,
                        )
                    ]
                ),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/stove_00.png",
                    z_index=4,
                    overlay_sprite="src/items/materials/misc/pot.png",
                    overlay_mode="center",
                    overlay_scale=0.58,
                ),
            ],
        )
        delivery_hatch = Entity(
            name="Delivery Hatch",
            position=Position_2D(9, 2),
            tags=["blocker", "station", "serve"],
            components=[
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/cabnet_00.png", z_index=4),
            ],
        )
        north_pass_counter = Entity(
            name="North Pass Counter",
            position=Position_2D(4, 7),
            tags=["blocker", "station", "counter"],
            components=[
                Single_Item_Holder(accepted_item_tags=["ingredient", "prepared_food", "dish", "plate"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_6.png", z_index=4),
            ],
        )
        lower_plate_pass = Entity(
            name="Lower Plate Pass",
            position=Position_2D(8, 7),
            tags=["blocker", "station", "counter"],
            components=[
                Single_Item_Holder(accepted_item_tags=["ingredient", "prepared_food", "dish", "plate"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(
                    sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/cabnet_01.png",
                    z_index=4,
                    overlay_sprite="src/items/equipment/armor/mirror_plate.png",
                    overlay_mode="center",
                    overlay_scale=0.42,
                ),
            ],
        )
        upper_divider_table = Entity(
            name="Upper Divider Table",
            position=Position_2D(5, 2),
            tags=["blocker", "station", "counter"],
            components=[
                Single_Item_Holder(accepted_item_tags=["ingredient", "prepared_food", "dish", "plate"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_6.png", z_index=4),
            ],
        )
        lower_divider_table = Entity(
            name="Lower Divider Table",
            position=Position_2D(5, 6),
            tags=["blocker", "station", "counter"],
            components=[
                Single_Item_Holder(accepted_item_tags=["ingredient", "prepared_food", "dish", "plate"]),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/world_tiles/indoors/appliances/PokemonGen2/table_6.png", z_index=4),
            ],
        )
        kitchen_window = Entity(
            name="Kitchen Window",
            position=Position_2D(10, 7),
            tags=["fixture"],
            components=[Renderable(sprite_path="src/world_tiles/indoors/architecture/window_center.png", z_index=5)],
        )
        prep_cook = Entity(
            name="Prep Cook",
            position=Position_2D(1, 4),
            tags=["agent", "chef"],
            actions=list(self.AGENT_ACTIONS),
            components=[
                Inventory(collectable_tags=["collectable"], inventory_size=1),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/characters/humanoids/human/farmer_man.png", z_index=10),
            ],
        )
        prep_cook.is_agent = True
        expediter = Entity(
            name="Expediter",
            position=Position_2D(9, 4),
            tags=["agent", "chef"],
            actions=list(self.AGENT_ACTIONS),
            components=[
                Inventory(collectable_tags=["collectable"], inventory_size=1),
                Collidable(collidable_tags=["blocker"]),
                Renderable(sprite_path="src/characters/humanoids/dwarven/gnome_wizard.png", z_index=10),
            ],
        )
        expediter.is_agent = True
        self.wall_positions = {
            (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0), (12, 0),
            (0, 1), (6, 1), (12, 1),
            (0, 2), (6, 2), (12, 2),
            (0, 3), (6, 3), (12, 3),
            (0, 4), (6, 4), (12, 4),
            (0, 5), (6, 5), (12, 5),
            (0, 6), (6, 6), (12, 6),
            (0, 7), (6, 7), (12, 7),
            (0, 8), (1, 8), (2, 8), (3, 8), (4, 8), (5, 8), (6, 8), (7, 8), (8, 8), (9, 8), (10, 8), (11, 8), (12, 8),
        }
        walls = [
            Entity(
                name=f"Wall {x},{y}",
                position=Position_2D(x, y),
                tags=["blocker", "wall"],
                components=[
                    Collidable(collidable_tags=["blocker"]),
                    Renderable(
                        sprite_path="src/world_tiles/indoors/wall_sets/overcooked_kitchen_wall/overcooked_kitchen_wall_center.png",
                        visible=False,
                    ),
                ],
            )
            for x, y in sorted(self.wall_positions)
        ]
        super().__init__(
            description="A small preset-based kitchen example.",
            entities=[
                prep_cook,
                expediter,
                tomato_counter,
                protein_fridge,
                plate_stack,
                chopping_board,
                stove,
                delivery_hatch,
                north_pass_counter,
                lower_plate_pass,
                upper_divider_table,
                lower_divider_table,
                kitchen_window,
                *walls,
            ],
            movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
            reward_func=team_reward,
            entity_order=entity_definition_order,
        )

    def render(self) -> None:
        if self.renderer_impl is None:
            raise NotImplementedError("This environment does not have a renderer attached.")
        self.renderer_impl.render(self)

    def observe(self, agent_id: int) -> Simple_Observation:
        return Simple_Observation(
            possible_actions=self.possible_actions(self.agents[agent_id]),
            agent=self.agents[agent_id],
            nearby_entities=[],
            last_reward=0.0 if self.last_rewards[agent_id] is None else self.last_rewards[agent_id],
            info=self.infos[agent_id],
        )

    def environment_start_of_step(self, action_selections: list[Action_Selection]) -> None:
        self.tick += 1
        self.step_score_delta = 0

    def environment_end_of_step(self, action_selections: list[Action_Selection]) -> None:
        if not self.order_queue:
            self.terminations = [True] * len(self.agents)
        if self.tick >= self.episode_length:
            self.truncations = [True] * len(self.agents)

__all__ = [
    "OvercookedKitchenEnv",
]
