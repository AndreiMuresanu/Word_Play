from word_play.core import (
    Agent_Policy,
    Entity,
)
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.random_action import Random_Action_Policy
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
from word_play.presets.renderers import (
    Grid_Layout_Adapter,
    Pygame_Renderer,
    Renderable,
)
from word_play.presets.systems.combat import Attack
from word_play.presets.systems.communication import (
    TalkingCow,
)
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import Inventory
from word_play.utils import tilemap_to_entities

import time
from concurrent.futures import ThreadPoolExecutor


def run_exp():
    exp_steps = 1000
    renderer = Pygame_Renderer(
        Grid_Layout_Adapter(),
        tile_size=56,
        default_floor_sprite="sprite_library/src/world_tiles/indoors/floors/day_grass_floor_c.png",
    )

    entity_tilemap = """
    WWWWWWWW...
    Wb.bs.cW...
    Wcbs.cbWWWW
    Wbcb.b..bsW
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
        "b": {
            "name": "Barbarian",
            "actions": [
                Do_Nothing(),
                Move_Up(),
                Move_Down(),
                Move_Left(),
                Move_Right(),
                Attack(name="Zap", damage_amount=1),
            ],
            "components": [
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
                Renderable(sprite_path="sprite_library/src/characters/monsters/misc/barbarian.png", z_index=10),
            ],
        },
        "c": {
            "name": "Cow",
            "actions": [Move_Up(), Move_Down()],
            "components": [
                Health(max_health=5, starting_health=5),
                Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
                TalkingCow(),
                Collidable(collidable_tags=["wall"]),
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
        description="The gladiator arena.",
        entities=tilemap_to_entities(entity_tilemap, entity_tileset),
        entity_order=randomize_agent_order,
        observation_radius=1,
        renderer=renderer,
    )

    for step in range(exp_steps):
        time.sleep(0.5)

        render_result = env.render()
        if render_result.quit_requested:
            break
        if render_result.reset_requested:
            env.reset()
            continue

        if env.agents:
            observations = [env.observe(agent_id) for agent_id in range(len(env.agents))]

            with ThreadPoolExecutor(max_workers=len(env.agents)) as executor:
                results = list(
                    executor.map(
                        lambda args: args[0].get_component(Agent_Policy).select_action(args[1]),
                        zip(env.agents, observations),
                    )
                )
            actions, infos = map(list, zip(*results))

        else:
            actions = []

        env.step(actions)


if __name__ == "__main__":
    run_exp()
