from word_play.environment import Environment, Action_Selection
from word_play.renderer import AsciiRenderer
from environments.collaborative_cooking.env import CollaborativeCookingEnv
from environments.collaborative_cooking.actions import Wait, Move_Forward, Turn_Left, Turn_Right, Interact
from environments.collaborative_cooking.agents import Chef, HeuristicChef
import random
import time

def run_sim(env: Environment, step_count: int):
    renderer = AsciiRenderer(env)
    print(f"Starting Simulation for {step_count} steps.")
    
    # Configure Agents with Heuristics
    # We dynamically upgrade the FocalAgents to HeuristicChefs for this experiment
    targets_0 = ["T", "X"] # Fetch Tomato, Put on Counter (X is Counter with item?) No, Counter is 'C'. X is only when holding item. Wait, 'C' is empty.
    # Agent 0: Go to Dispenser (T), Interact, then Go to Counter (C), Interact.
    # Agent 1: Go to Counter (X i.e. holding item), Interact, Go to Pot (P), Interact.
    
    # Wait, 'X' symbol logic relies on item presence. If empty, it's 'C'.
    # Heuristic logic scans for char.
    # We give them a sequence of targets to cycle through? 
    # Current Heuristic implementation cycles targets index.
    
    # Let's set targets.
    if len(env.agents) >= 2:
        # Agent 0 (Left)
        env.agents[0].__class__ = HeuristicChef
        env.agents[0].targets = ["T", "X"] 
        env.agents[0].current_goal_index = 0
        
        # Agent 1 (Right)
        env.agents[1].__class__ = HeuristicChef
        env.agents[1].targets = ["X", "C", "P"] # Look for Counter-with-item (X), then Counter (C), then Pot (P)
        env.agents[1].current_goal_index = 0

    # Ensure current_goal_index advances on successful interaction?
    # The simple heuristic doesn't handle state changes well (just cycles). 
    # We might need to manually nudge index based on holding state in the loop.
    
    # Render Initial State
    print("\n--- Initial State ---")
    renderer.render()
    
    for step in range(step_count):
        print(f"\n--- Step {step} ---")
        this_rounds_actions = []
        
        for agent_id, agent in enumerate(env.agents):
            observation = env.observe(agent_id)
            
            # Update Heuristic State based on Holding
            if isinstance(agent, HeuristicChef):
                if agent_id == 0:
                    # If holding Tomato, target C. Else target T.
                    if agent.state.holding == "Tomato": agent.current_goal_index = 1
                    else: agent.current_goal_index = 0
                elif agent_id == 1:
                    # If holding Tomato, target P. Else target X (Counter with Tomato).
                    if agent.state.holding == "Tomato": agent.current_goal_index = 1 # P
                    else: agent.current_goal_index = 0 # X
            
            # Select Action
            action_sel, _ = agent.select_action(observation)
            action = action_sel.action
            
            print('>>>>>>>>>>>>>>> info start >>>>>>>>>>>>>>>')
            print('agent_id:', agent_id)
            obs_str = str(observation)
            print('observation summary:', obs_str[:50] + "..." if len(obs_str) > 50 else obs_str)
            print('action:', action)
            print('<<<<<<<<<<<<<<< info end <<<<<<<<<<<<<<<')
            
            this_rounds_actions.append(action_sel)
            
        env.step(this_rounds_actions)
        renderer.render()
        time.sleep(0.5)

if __name__ == '__main__':
    # Define a simple layout for the experiment
    layout = """
#######
#T C P#
#     #
#S   S#
#######
"""
    # Initialize the environment
    # CollaborativeCookingEnv parses the layout and creates entities (Walls, Pots, Agents, etc.)
    env = CollaborativeCookingEnv(layout.strip(), num_focal_agents=2)
    
    print("Environment Created.")
    print(f"Entities: {len(env.state.entities)}")
    print(f"Agents: {len(env.agents)}")
    
    # Run the simulation
    run_sim(env=env, step_count=20)
