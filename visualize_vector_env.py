import sys
import random
import os

# Ensure the project root is in sys.path if running from root
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from word_play.environment import Environment_State, Environment_Properties, Entity_State
from environments.complex_test_env.env import ComplexTestEnv
from environments.complex_test_env.entities import SmartAgent, SmartAgentProperties, Obstacle, SimpleEntityProperties, Gold, Trap
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D
from word_play.renderer import render_vector_envs

def dummy_reward(action_selections, env): return [0.0]

def create_large_env(index):
    """
    Creates a 13x13 environment (0,0 to 12,12) with random clutter.
    """
    entities = []
    
    # Corners to define size visually (Top-Left and Bottom-Right)
    entities.append(Obstacle(Entity_State(Position_2D(0, 0)), SimpleEntityProperties(name="Corner", symbol="#")))
    entities.append(Obstacle(Entity_State(Position_2D(12, 12)), SimpleEntityProperties(name="Corner", symbol="#")))
    
    # Random Agent
    ax, ay = random.randint(1, 11), random.randint(1, 11)
    entities.append(SmartAgent(
        state=Entity_State(Position_2D(ax, ay)), 
        properties=SmartAgentProperties(name=f"A{index}", symbol="A", color="GREEN")
    ))
    
    # Random Clutter (Gold/Traps)
    for _ in range(4): # 4 pieces of gold
        gx, gy = random.randint(1, 11), random.randint(1, 11)
        entities.append(Gold(Entity_State(Position_2D(gx, gy)), SimpleEntityProperties(name="Gold", symbol="G", color="YELLOW")))
    
    for _ in range(2): # 2 traps
        tx, ty = random.randint(1, 11), random.randint(1, 11)
        entities.append(Trap(Entity_State(Position_2D(tx, ty)), SimpleEntityProperties(name="Trap", symbol="X", color="RED")))

    env_state = Environment_State(entities=entities)
    env = ComplexTestEnv(
        state=env_state,
        properties=Environment_Properties(f"Sim {index}"),
        movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
        reward_func=dummy_reward
    )
    return env

if __name__ == "__main__":
    count = 100
    print(f"Initializing {count} Large (13x13) environments...")
    envs = [create_large_env(i) for i in range(count)]

    print(f"\nRendering {count} Environments in a Grid...")
    # Render with 5 columns
    render_vector_envs(envs, cols=5, count=count, clear=False)
