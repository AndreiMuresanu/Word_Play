import random
from word_play.environment import Environment_State, Environment_Properties, Entity_State
from environments.complex_test_env.env import ComplexTestEnv
from environments.complex_test_env.entities import SmartAgent, SmartAgentProperties, Obstacle, SimpleEntityProperties, Gold, Trap
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D

def dummy_reward(action_selections, env): return [0.0]

def create_env(index):
    entities = []
    # Corners
    entities.append(Obstacle(Entity_State(Position_2D(0, 0)), SimpleEntityProperties(name="Corner", symbol="#")))
    entities.append(Obstacle(Entity_State(Position_2D(5, 5)), SimpleEntityProperties(name="Corner", symbol="#")))
    
    # Random Agent
    entities.append(SmartAgent(
        state=Entity_State(Position_2D(random.randint(1, 4), random.randint(1, 4))), 
        properties=SmartAgentProperties(name=f"A{index}", symbol="A", color="GREEN")
    ))
    
    # Gold
    entities.append(Gold(Entity_State(Position_2D(random.randint(1, 4), random.randint(1, 4))), SimpleEntityProperties(name="Gold", symbol="G", color="YELLOW")))

    env_state = Environment_State(entities=entities)
    env = ComplexTestEnv(
        state=env_state,
        properties=Environment_Properties(f"Sim {index}"),
        movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
        reward_func=dummy_reward
    )
    return env

def run_demo():
    print("Initializing environments...")
    
    envs = [create_env(i) for i in range(8)]
    base_env = envs[0] # Just use the first one as the caller
    
    print("\n--- Testing env.render(envs=envs, number_of_environments=6) ---")
    # Use the base_env to trigger the vector render
    base_env.render(envs=envs, number_of_environments=6, clear=False)

    print("\n--- Testing return_string=True ---")
    output = base_env.render(envs=envs, number_of_environments=4, return_string=True, clear=False)
    if output:
        print("Captured String Length:", len(output))
        print("First 100 chars of output:")
        print(output[:100])
    else:
        print("Error: Output is None")

if __name__ == "__main__":
    run_demo()
