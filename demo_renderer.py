import sys
import time
import random

# Ensure the project root is in sys.path
sys.path.append('/Users/iamsogoodlo/Documents/Projects/Word_Play')

from word_play.environment import Environment_State, Environment_Properties, Entity_State
from environments.complex_test_env.env import ComplexTestEnv
from environments.complex_test_env.entities import SmartAgent, SmartAgentProperties, Gold, Trap, Obstacle, SimpleEntityProperties
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D, Move_Right, Move_Left, Move_Up, Move_Down

def dummy_reward(action_selections, env):
    return [0.0]

# Setup Entities
entities = []
agent_props = SmartAgentProperties(name="Agent", symbol="A", color="GREEN")
gold_props = SimpleEntityProperties(name="Gold", symbol="G", color="YELLOW")
trap_props = SimpleEntityProperties(name="Trap", symbol="X", color="RED")
wall_props = SimpleEntityProperties(name="Wall", symbol="#", color="WHITE")

# Place Agents
entities.append(SmartAgent(Entity_State(Position_2D(1, 8)), agent_props))
entities.append(SmartAgent(Entity_State(Position_2D(8, 8)), agent_props))
entities.append(SmartAgent(Entity_State(Position_2D(5, 5)), agent_props))

# Place Items
entities.append(Gold(Entity_State(Position_2D(1, 1)), gold_props))
entities.append(Trap(Entity_State(Position_2D(8, 1)), trap_props))
entities.append(Obstacle(Entity_State(Position_2D(4, 5)), wall_props))

env_state = Environment_State(entities=entities)
env_props = Environment_Properties(description="Interactive Demo Environment")

env = ComplexTestEnv(
    state=env_state,
    properties=env_props,
    movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
    reward_func=dummy_reward
)

print("\n--- Starting Simulation (3 Steps) ---\n")
env.render()

for step in range(3):
    time.sleep(1)
    print(f"\n--- Step {step + 1} ---")
    
    # Simple random movement for agents
    for entity in env.state.entities:
        if isinstance(entity, SmartAgent):
            move = random.choice([Move_Right(), Move_Left(), Move_Up(), Move_Down()])
            move(entity, env)
            
    env.render()

print("\n--- Simulation Complete ---")
