from word_play.core import Entity
from word_play.presets.action_policies.human import Human_Takes_Action
from word_play.presets.environments.simple_2d_grid_world import Simple_2D_Grid_World
from word_play.presets.movement.simple_2d_grid import Move_Down, Move_Left, Move_Right, Move_Up, Position_2D
from word_play.presets.systems.do_nothing import Do_Nothing

import sys


def run_demo(observation_radius: int = 1):
    agent = Entity(
        name="Observer",
        position=Position_2D(0, 0),
        actions=[Do_Nothing(), Move_Up(), Move_Down(), Move_Left(), Move_Right()],
        components=[Human_Takes_Action()],
    )

    env = Simple_2D_Grid_World(
        description="Observation radius demo",
        entities=[
            agent,
            Entity(name="Center Item", position=Position_2D(0, 0), tags=["item"]),
            Entity(name="Near NE", position=Position_2D(1, 1), tags=["item"]),
            Entity(name="Near West", position=Position_2D(-1, 0), tags=["item"]),
            Entity(name="Far East", position=Position_2D(3, 0), tags=["item"]),
            Entity(name="Far South", position=Position_2D(0, -3), tags=["item"]),
        ],
        observation_radius=observation_radius,
    )

    print(f"Observation radius demo with radius={observation_radius}\n")
    print(env.observe(0))


if __name__ == "__main__":
    radius = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run_demo(radius)
