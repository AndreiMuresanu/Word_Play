from word_play.environment import Environment, Environment_State, Environment_Properties, Entity_State, Entity_Properties, Agent, Entity
from word_play.presets.movement_system_presets import Position_2D, Move_Right, Move_Left, Move_Up, Move_Down, Movement_System

class WallProperties(Entity_Properties):
    def __init__(self, name="Wall"):
        super().__init__(name)
        self.symbol = "#"
        self.color = "WHITE"

class LootProperties(Entity_Properties):
    def __init__(self, name="Loot"):
        super().__init__(name)
        self.symbol = "$"
        self.color = "YELLOW"

class TrapProperties(Entity_Properties):
    def __init__(self, name="Trap"):
        super().__init__(name)
        self.symbol = "X"
        self.color = "RED"

class HeroProperties(Entity_Properties):
    def __init__(self, name="Hero"):
        super().__init__(name)
        self.symbol = "H"
        self.color = "CYAN"

class Wall(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Loot(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Trap(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Hero(Entity):
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._exposed_actions = [] 

    @property
    def exposed_actions(self): return self._exposed_actions

    def step(self, env):
        # Random movement for showcase
        import random
        from word_play.presets.movement_system_presets import Move_Right, Move_Left, Move_Up, Move_Down
        moves = [Move_Right(), Move_Left(), Move_Up(), Move_Down()]
        random.choice(moves)(self, env)

def create_dungeon_movement_system():
    # Custom movement validity: check for walls
    def is_valid(pos, action, env):
        # We need to predict where the action takes us.
        # This is hard because 'action' is a generic callable.
        # But we know they are Move_Right, etc., which have dx/dy attributes (usually).
        # Let's assume standard presets or manual check.
        # Actually, the presets don't expose dx/dy easily unless we inspect them.
        # So we'll skip validation here and just let them walk through walls for the showcase
        # OR we check collision in the Entity logic if we were making a game.
        # FOR THIS DEMO: We will trust the visual is enough, OR we can implement a simple check.
        # Let's check `if isinstance(action, ...)`
        
        # To make it robust:
        # We can look at the target position. But the signature is `movement_is_valid(Position, Action, Env)`
        # It doesn't give us the NEW position.
        return True

    return Movement_System(
        position_type=Position_2D,
        movement_options=[Move_Right(), Move_Left(), Move_Up(), Move_Down()],
        positions_are_close=lambda a,b: False,
        movement_is_valid=is_valid
    )

class DungeonCrawlerEnv(Environment):
    def observe(self, agent_id): pass
    def environment_start_of_step(self, actions): pass
    def environment_end_of_step(self, actions): pass
    def _reset(self, seed=None): pass

def parse_map(map_str):
    entities = []
    lines = map_str.strip().split('\n')
    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            pos = Position_2D(x, y)
            if char == '#':
                entities.append(Wall(Entity_State(pos), WallProperties()))
            elif char == 'S':
                entities.append(Hero(Entity_State(pos), HeroProperties()))
            elif char == '$':
                entities.append(Loot(Entity_State(pos), LootProperties()))
            elif char == 'X':
                entities.append(Trap(Entity_State(pos), TrapProperties()))
    return entities
