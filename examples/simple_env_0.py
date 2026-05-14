from word_play.core import (
    Agent_Policy,
    Entity,
)
from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import (
    Collidable,
    Move_Up,
    Move_Down,
    Move_Left,
    Move_Right,
    Position_2D,
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


def run_exp():
    exp_steps = 1000

    env = Simple_2D_Grid_World(
        description="The forbidden forest.",
        entities=[
            Entity(
                name="Iskandar",
                position=Position_2D(0, 0),
                actions=[
                    Do_Nothing(),
                    Move_Up(),
                    Move_Down(),
                    Move_Left(),
                    Move_Right(),
                    Attack(name="Zap", damage_amount=1),
                    Start_Public_Conversation(),
                    Start_Private_Conversation(),
                ],
                components=[
                    Human_Takes_Action(),
                    Inventory(
                        collectable_tags=["item"],
                        inventory_size=2,
                        starting_inventory=[Entity(name="Strawberry", position=Position_2D(100, 100), tags=["item"])],
                    ),
                    Health(max_health=5, starting_health=3),
                    Collidable(collidable_tags=["wall"]),
                    Human_Communication_Policy(),
                ],
            ),
            Entity(name="Blue Flower", position=Position_2D(0, 1), tags=["item"]),
            Entity(
                name="Barrel",
                position=Position_2D(0, 0),
                tags=["item"],
                components=[Health(max_health=1, starting_health=1)],
            ),
            Entity(
                name="Barrel",
                position=Position_2D(0, 1),
                tags=["item"],
                components=[Health(max_health=1, starting_health=1)],
            ),
            Entity(
                name="Cow",
                position=Position_2D(1, 0),
                actions=[Move_Up(), Move_Down()],
                components=[
                    Health(max_health=5, starting_health=5),
                    Follow_Action_Sequence([(Move_Up, None), (Move_Down, None)]),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Fat Cow",
                position=Position_2D(1, 0),
                components=[
                    Health(max_health=10, starting_health=10),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Tiny Cow",
                position=Position_2D(1, 0),
                components=[
                    Health(max_health=1, starting_health=1),
                    TalkingCow(),
                ],
            ),
            Entity(
                name="Wall",
                position=Position_2D(-1, 0),
                tags=["wall"],
                components=[Collidable()],
            ),
            Entity(
                name="Spike",
                position=Position_2D(0, -2),
                actions=[Attack(name="Poke", damage_amount=1)],
                tags=["item"],
                components=[Follow_Action_Sequence([(Attack, None)])],
            ),
        ],
    )

    for step in range(exp_steps):
        cur_step_actions = []
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            action, info = agent.get_component(Agent_Policy).select_action(observation)
            print(f"[step {step}] {agent.name} -> {action}")
            cur_step_actions.append(action)

        env.step(cur_step_actions)


if __name__ == "__main__":
    run_exp()
