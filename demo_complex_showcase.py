import time
import random
from word_play.renderer import AsciiRenderer
from word_play.environment import Environment_State, Environment_Properties, Entity_State, Entity_Properties
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D

# 1. Predator Prey Imports
from environments.showcase_envs.predator_prey import PredatorPreyEnv, Predator, PreyEntity, PredatorEntity, PredatorProperties, PreyProperties, SmartEntity

# 2. Dungeon Crawler Imports
from environments.showcase_envs.dungeon_crawler import DungeonCrawlerEnv, create_dungeon_movement_system, parse_map

# 3. Resource Gathering Imports
from environments.showcase_envs.resource_gathering import ResourceGatheringEnv, Gatherer

def create_predator_prey():
    entities = []
    # 2 Predators
    entities.append(PredatorEntity(Entity_State(Position_2D(1, 1)), PredatorProperties("Wolf1")))
    entities.append(PredatorEntity(Entity_State(Position_2D(8, 8)), PredatorProperties("Wolf2")))
    
    # 5 Prey
    for i in range(5):
        entities.append(PreyEntity(Entity_State(Position_2D(random.randint(2, 7), random.randint(2, 7))), PreyProperties(f"Bunny{i}")))
        
    return PredatorPreyEnv(
        state=Environment_State(entities),
        properties=Environment_Properties("Predator vs Prey"),
        movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
        reward_func=lambda *args: [0]
    )

def create_dungeon():
    # Simple map
    map_str = \
"""
##########
#S.......#
###.####.#
#...#..$.#
#.###.##.#
#$....X..#
##########
"""
    entities = parse_map(map_str)
    # The 'S' in map spawns a Hero, but the parser spawns it as generic 'Hero'
    # We rely on the parser from dungeon_crawler.py
    return DungeonCrawlerEnv(
        state=Environment_State(entities),
        properties=Environment_Properties("Dungeon Crawler"),
        movement_system=create_dungeon_movement_system(),
        reward_func=lambda *args: [0]
    )

def create_resource_gathering():
    entities = []
    # 3 Gatherers
    for i in range(3):
        entities.append(Gatherer(Entity_State(Position_2D(5, 5)), Entity_Properties(f"Gatherer{i}")))
    
    return ResourceGatheringEnv(
        state=Environment_State(entities),
        properties=Environment_Properties("Resource Rush"),
        movement_system=INFINITE_2D_MOVEMENT_SYSTEM,
        reward_func=lambda *args: [0]
    )

def run_showcase():
    print("Initializing Showcase...")
    envs = [
        create_predator_prey(),
        create_dungeon(),
        create_resource_gathering()
    ]
    
    renderer = AsciiRenderer(envs, cols=3)
    
    print("Starting Simulation Loop (20 steps)...")
    for step in range(20):
        # 1. Clear & Render
        renderer.render(clear=True, show_legend=True)
        print(f"Step: {step+1}/20")
        
        # 2. Step Environments
        # We manually step them to ensure our custom logic runs
        for env in envs:
            env.step([]) # Pass empty actions, let internal logic handle movement
            
        time.sleep(0.5)

    print("Showcase Complete!")

if __name__ == "__main__":
    run_showcase()
