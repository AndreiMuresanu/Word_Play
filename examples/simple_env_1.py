from word_play.core import (
    Action,
    Agent_Policy,
    Entity,
    Target_Is_Self,
)
from word_play.presets.action_args import (
    Dict_Arg,
    Int_Arg,
    List_Arg,
    String_Arg,
    String_Choice_Arg,
)
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.action_policies.random_action import Random_Action_Policy
from word_play.presets.entity_orderings import randomize_agent_order
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import (
    Collidable,
    Move_Up,
    Move_Down,
    Move_Left,
    Move_Right,
    Position_2D,
)
from word_play.presets.renderers import (
    Grid_Layout_Adapter,
    Pygame_Renderer,
    Renderable,
)
from word_play.presets.systems.combat import Attack
from word_play.presets.systems.communication import (
    Human_Communication_Policy,
    Start_Private_Conversation,
    Start_Public_Conversation,
    TalkingCow,
)
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import Inventory
from word_play.utils import tilemap_to_entities

import pprint


class Test_Action(Action):

    def __init__(self):
        super().__init__(
            validation_rules=[Target_Is_Self()],
            required_kwargs={
                "gold coin count": Int_Arg(),
                "assignment": Dict_Arg(String_Arg(), Int_Arg()),
                "damages": List_Arg(Int_Arg()),
                "item": String_Choice_Arg({"hammer", "apple"}),
            },
        )

    def exec_action(self, actor, target_entity, env, kwargs):
        print("=======")
        pprint.pprint(kwargs, sort_dicts=False)
        print("=======")

    def action_description_text(self, actor, target_entity, env):
        return "Test Action."


def run_exp():
    exp_steps = 1000
    renderer = Pygame_Renderer(
        Grid_Layout_Adapter(),
        tile_size=56,
        default_floor_sprite="sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png",
    )
    entity_tilemap = """
    WWWWWWWW...
    Wb.h...W...
    WAfs.t.WWWW
    WIc..b....W
    WWWWWWWWWWW
    """
    entity_tileset = {
        "W": {
            "name": "Wall",
            "tags": ["wall"],
            "components": [
                Collidable(),
                Renderable(
                    sprite_path="sprite_library/src/world_tiles/indoors/wall_sets/dim_brick_wall/dim_brick_wall_center.png",
                    wall_set="sprite_library/src/world_tiles/indoors/wall_sets/dim_brick_wall",
                ),
            ],
        },
        "I": {
            "name": "Iskandar",
            "actions": [
                Test_Action(),
                Do_Nothing(),
                Move_Up(),
                Move_Down(),
                Move_Left(),
                Move_Right(),
                Attack(name="Zap", damage_amount=1),
                Start_Public_Conversation(),
                Start_Private_Conversation(),
            ],
            "components": [
                Human_Takes_Action(),
                Inventory(
                    collectable_tags=["item"],
                    inventory_size=2,
                    starting_inventory=[
                        Entity(
                            name="Strawberry",
                            position=Position_2D(100, 100),
                            tags=["item"],
                            components=[
                                Renderable(
                                    sprite_path="sprite_library/src/items/consumables/fruit/strawberry_2.png",
                                    z_index=2,
                                )
                            ],
                        )
                    ],
                ),
                Health(max_health=5, starting_health=3),
                Collidable(collidable_tags=["wall"]),
                Human_Communication_Policy(),
                Renderable(sprite_path="sprite_library/src/characters/humanoids/human/ordinary_human.png", z_index=10),
            ],
        },
        "A": {
            "name": "Andrei",
            "actions": [
                Test_Action(),
                Do_Nothing(),
                Move_Up(),
                Move_Down(),
                Move_Left(),
                Move_Right(),
                Attack(name="Zap", damage_amount=1),
                # Start_Public_Conversation(),
                # Start_Private_Conversation(),
            ],
            "components": [
                # Human_Takes_Action(),
                Random_Action_Policy(),
                Inventory(
                    collectable_tags=["item"],
                    inventory_size=2,
                    starting_inventory=[
                        Entity(
                            name="Strawberry",
                            position=Position_2D(100, 100),
                            tags=["item"],
                            components=[
                                Renderable(
                                    sprite_path="sprite_library/src/items/consumables/fruit/strawberry_2.png",
                                    z_index=2,
                                )
                            ],
                        )
                    ],
                ),
                Health(max_health=5, starting_health=3),
                Collidable(collidable_tags=["wall"]),
                Human_Communication_Policy(),
                Renderable(sprite_path="sprite_library/src/characters/monsters/misc/archaeologist.png", z_index=10),
            ],
        },
        "f": {
            "name": "Blue Flower",
            "tags": ["item"],
            "components": [
                Renderable(sprite_path="sprite_library/src/characters/flora/plant/twoflower.png", z_index=2)
            ],
        },
        "b": {
            "name": "Barrel",
            "tags": ["item"],
            "components": [
                Health(max_health=1, starting_health=1),
                Renderable(sprite_path="sprite_library/src/items/materials/misc/closed_barrel.png", z_index=2),
            ],
        },
        "c": {
            "name": "Cow",
            "actions": [Move_Up(), Move_Down()],
            "components": [
                Health(max_health=5, starting_health=5),
                Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
                TalkingCow(),
                Renderable(sprite_path="sprite_library/src/characters/monsters/misc/dairy_cow.png", z_index=8),
            ],
        },
        "h": {
            "name": "Fat Cow",
            "components": [
                Health(max_health=10, starting_health=10),
                TalkingCow(),
                Renderable(sprite_path="sprite_library/src/characters/monsters/misc/dairy_cow.png", z_index=8),
            ],
        },
        "t": {
            "name": "Tiny Cow",
            "components": [
                Health(max_health=1, starting_health=1),
                TalkingCow(),
                Renderable(sprite_path="sprite_library/src/characters/monsters/misc/dairy_cow.png", z_index=8),
            ],
        },
        "s": {
            "name": "Spike",
            "actions": [Attack(name="Poke", damage_amount=1)],
            "tags": ["item"],
            "components": [
                Follow_Action_Sequence([(Attack, None)]),
                Renderable(sprite_path="sprite_library/src/items/materials/misc/spikes.png", z_index=2),
            ],
        },
    }

    env = Simple_2D_Grid_World(
        description="The forbidden forest.",
        entities=tilemap_to_entities(entity_tilemap, entity_tileset),
        entity_order=randomize_agent_order,
        observation_radius=1,
        renderer=renderer,
    )

    for step in range(exp_steps):
        render_result = env.render()
        if render_result.quit_requested:
            break
        if render_result.reset_requested:
            env.reset()
            continue

        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp()
