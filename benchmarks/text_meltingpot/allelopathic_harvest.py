import argparse
import random

from word_play.core import (
    Action,
    Action_Selection,
    Agent_Policy,
    Entity,
)
from word_play.presets.action_policies.llm_action_and_communication import LLM_Action_And_Communication_Policy
from word_play.presets.action_policies.random_policy import Random_Policy
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
    Renderable,
    render_step,
)
from word_play.presets.systems.containers import (
    Regrowable_Item_Source,
    Take_From_Infinite_Source,
)
from word_play.presets.systems.cooldown import (
    Action_On_Cooldown,
    Cooldown,
)
from word_play.presets.systems.crafter import Zap_Change
from word_play.presets.systems.do_nothing import Do_Nothing
from word_play.presets.systems.freezable import Freezable
from word_play.presets.systems.health import Health
from word_play.presets.systems.inventory import Inventory
from word_play.presets.systems.preferences import Preference
from word_play.presets.systems.zap import (
    ZapMarking,
    Zap_Player,
)
from word_play.presets.models import (
    LLM_MODEL_REGISTRY,
    OpenRouter_Model,
)
from word_play.utils import tilemap_to_entities
from word_play.utils.tilemap import find_tile_positions


class Paint_Berry(Action):

    def __init__(self, color: str):
        super().__init__(validation_rules=[Action_On_Cooldown("color")])
        self.color = color
        self.zap_change = Zap_Change(
            allowed_tag="berry_patch",
            output=lambda: Entity(
                name=f"{color.title()} Berry Patch",
                position=Position_2D(0, 0),
                tags=["berry_patch", "berry", color],
                components=[
                    Regrowable_Item_Source(
                        item_factory=Entity(
                            name=f"{color.title()} Berry",
                            position=Position_2D(0, 0),
                            tags=["berry", color],
                            components=[
                                Renderable(
                                    sprite_path="src/items/consumables/vegetables/mushroom_red.png"
                                    if color == "red"
                                    else "src/items/consumables/vegetables/mushroom_green.png"
                                    if color == "green"
                                    else "src/items/consumables/vegetables/mushroom_blue.png",
                                    z_index=5,
                                )
                            ],
                        ),
                        max_capacity=1,
                        regen_rate=1,
                    ),
                    Renderable(
                        sprite_path="src/items/consumables/vegetables/mushroom_red.png"
                        if color == "red"
                        else "src/items/consumables/vegetables/mushroom_green.png"
                        if color == "green"
                        else "src/items/consumables/vegetables/mushroom_blue.png",
                        z_index=2,
                    ),
                ],
            ),
        )

    def is_valid(self, actor, target_entity, env, kwargs="unconsidered") -> bool:
        return super().is_valid(actor, target_entity, env, kwargs=kwargs) and self.zap_change.is_valid(
            actor,
            target_entity,
            env,
            kwargs,
        )

    def exec_action(self, actor, target_entity, env, kwargs):
        actor.get_component(Cooldown).start("color")
        return self.zap_change.exec_action(actor, target_entity, env, kwargs)

    def action_description_text(self, actor, target_entity, env):
        return f"Paint {target_entity.name} {self.color}."


def run_exp(agent_count: int = 4, policy: str = "random"):
    exp_steps = 2000
    model_key = "allelopathic_harvest"

    if policy == "llm":
        LLM_MODEL_REGISTRY[model_key] = OpenRouter_Model(
            model_name="openai/gpt-4o-mini",
            generation_params={"temperature": 0.3},
        )

    entity_tilemap = """
    WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
    W333PPPP12PPP322P32PPP1P13P3P3W
    W1PPPP2PP122PPP3P232121P2PP2P1W
    WP1P3P11PPP13PPP31PPPP23PPPPPPW
    WPPPPP2P2P1P2P3P33P23PP2P2PPPPW
    WP1PPPPPPP2PPP12311PP3321PPPPPW
    W133P2PP2PPP3PPP1PPP2213P112P1W
    W3PPPPPPPPPPPPP31PPPPPP1P3112PW
    WPP2P21P21P33PPPPPPP3PP2PPPP1PW
    WPPPPP1P1P32P3PPP22PP1P2PPPP2PW
    WPPP3PP3122211PPP2113P3PPP1332W
    WPP12132PP1PP1P321PP1PPPPPP1P3W
    WPPP222P12PPPP1PPPP1PPP321P11PW
    WPPP2PPPP3P2P1PPP1P23322PP1P13W
    W23PPP2PPPP2P3PPPP3PP3PPP3PPP2W
    W2PPPP3P3P3PP3PP3P1P3PP11P21P1W
    W21PPP2PP331PP3PPP2PPPPP2PP3PPW
    WP32P2PP2P1PPPPPPP12P2PPP1PPPPW
    WP3PP3P2P21P3PP2PP11PP1323P312W
    W2P1PPPPP1PPP1P2PPP3P32P2P331PW
    WPPPPP1312P3P2PPPP3P32PPPP2P11W
    WP3PPPP221PPP2PPPPPPPP1PPP311PW
    W32P3PPPPPPPPPP31PPPP3PPP13PPPW
    WPPP3PPPPP3PPPPPP232P13PPPPPP1W
    WP1PP1PPP2PP3PPPPP33321PP2P3PPW
    WP13PPPP1P333PPPP2PP213PP2P3PPW
    W1PPPPP3PP2P1PP21P3PPPP231P2PPW
    W1331P2P12P2PPPP2PPP3P23P21PPPW
    WP3P131P3PPP13P1PPP222PPPP11PPW
    W2P3PPPPPPPP2P323PPP2PPP1PPP2PW
    W21PPPPPPP12P23P1PPPPPP13P3P11W
    WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
    """
    entity_tileset = {
        "W": {
            "name": "Wall",
            "tags": ["wall"],
            "components": [
                Collidable(collidable_tags=["wall"]),
                Renderable(
                    sprite_path="src/world_tiles/outdoors/terrain/wall_stone.png",
                    z_index=3,
                ),
            ],
        },
        "1": {
            "name": "Red Berry Patch",
            "tags": ["berry_patch", "berry", "red"],
            "components": [
                Regrowable_Item_Source(
                    item_factory=Entity(
                        name="Red Berry",
                        position=Position_2D(0, 0),
                        tags=["berry", "red"],
                        components=[
                            Renderable(
                                sprite_path="src/items/consumables/vegetables/mushroom_red.png",
                                z_index=5,
                            )
                        ],
                    ),
                    max_capacity=1,
                    regen_rate=1,
                ),
                Renderable(
                    sprite_path="src/items/consumables/vegetables/mushroom_red.png",
                    z_index=2,
                ),
            ],
        },
        "2": {
            "name": "Green Berry Patch",
            "tags": ["berry_patch", "berry", "green"],
            "components": [
                Regrowable_Item_Source(
                    item_factory=Entity(
                        name="Green Berry",
                        position=Position_2D(0, 0),
                        tags=["berry", "green"],
                        components=[
                            Renderable(
                                sprite_path="src/items/consumables/vegetables/mushroom_green.png",
                                z_index=5,
                            )
                        ],
                    ),
                    max_capacity=1,
                    regen_rate=1,
                ),
                Renderable(
                    sprite_path="src/items/consumables/vegetables/mushroom_green.png",
                    z_index=2,
                ),
            ],
        },
        "3": {
            "name": "Blue Berry Patch",
            "tags": ["berry_patch", "berry", "blue"],
            "components": [
                Regrowable_Item_Source(
                    item_factory=Entity(
                        name="Blue Berry",
                        position=Position_2D(0, 0),
                        tags=["berry", "blue"],
                        components=[
                            Renderable(
                                sprite_path="src/items/consumables/vegetables/mushroom_blue.png",
                                z_index=5,
                            )
                        ],
                    ),
                    max_capacity=1,
                    regen_rate=1,
                ),
                Renderable(
                    sprite_path="src/items/consumables/vegetables/mushroom_blue.png",
                    z_index=2,
                ),
            ],
        },
    }

    entities = tilemap_to_entities(entity_tilemap.replace("P", "."), entity_tileset)
    spawn_positions = find_tile_positions(entity_tilemap, "P")
    random.shuffle(spawn_positions)
    for agent_id, (x, y) in enumerate(spawn_positions[:agent_count], start=1):
        preferred_color = random.choice(["red", "green", "blue"])
        if policy == "llm":
            agent_policy = LLM_Action_And_Communication_Policy(
                model_key=model_key,
                system_prompt=(
                    f"You are Player {agent_id} in Allelopathic Harvest. "
                    f"You prefer {preferred_color} berries. "
                    "Move, harvest berries, repaint berry patches, and zap opponents to maximize reward."
                ),
                use_chain_of_thought=True,
                observation_memory_window=4,
                conversation_memory_window=8,
            )
        else:
            agent_policy = Random_Policy()
        entities.append(
            Entity(
                name=f"Player {agent_id}",
                position=Position_2D(x, y),
                tags=["agent", "player"],
                actions=[
                    Do_Nothing(),
                    Move_Up(),
                    Move_Down(),
                    Move_Left(),
                    Move_Right(),
                    Take_From_Infinite_Source(),
                    Zap_Player(),
                    Paint_Berry("red"),
                    Paint_Berry("green"),
                    Paint_Berry("blue"),
                ],
                components=[
                    agent_policy,
                    Inventory(max_size=5, accepted_tags=["berry"]),
                    Preference(reward_map={preferred_color: 2.0}, default_reward=1.0),
                    Cooldown(cooldowns={"zap": 4, "color": 2}),
                    Freezable(default_duration=25),
                    ZapMarking(freeze_duration=25, penalty=-10.0, recovery_time=50),
                    Health(max_health=2, starting_health=2),
                    Collidable(collidable_tags=["wall"]),
                    Renderable(
                        sprite_path="src/characters/humanoids/human/farmer_man.png",
                        z_index=10,
                    ),
                ],
            )
        )

    env = Simple_2D_Grid_World(
        description="Allelopathic harvest.",
        entities=entities,
        entity_order=randomize_agent_order,
        observation_radius=3,
    )

    for step in range(exp_steps):
        if not render_step(env, step_delay=0.0):
            break

        env.last_step_rewards = [0.0] * len(env.agents)
        env.reward_func = lambda action_selections, current_env: list(current_env.last_step_rewards)

        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-count", type=int, default=4)
    parser.add_argument("--policy", choices=["random", "llm"], default="random")
    args = parser.parse_args()
    run_exp(agent_count=args.agent_count, policy=args.policy)
