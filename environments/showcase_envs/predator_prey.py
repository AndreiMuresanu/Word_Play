import random
from word_play.environment import Environment, Environment_State, Environment_Properties, Entity_State, Entity_Properties, Agent, Entity
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D, Move_Right, Move_Left, Move_Up, Move_Down

class PredatorProperties(Entity_Properties):
    def __init__(self, name):
        super().__init__(name)
        self.symbol = "P"
        self.color = "RED"

class PreyProperties(Entity_Properties):
    def __init__(self, name):
        super().__init__(name)
        self.symbol = "b" # bunny
        self.color = "WHITE"

class SimpleAI_Agent(Agent):
    """Base class for simple movement AI."""
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._actions_on_self = [] 

    @property
    def actions_on_self(self):
        return self._actions_on_self
    
    @actions_on_self.setter
    def actions_on_self(self, value):
        self._actions_on_self = value

    @property
    def exposed_actions(self):
        return []

    def select_action(self, observation):
        # Not used in this simple simulation step logic
        return None, {}

    def step(self):
        pass

class Predator(SimpleAI_Agent):
    def step(self):
        # Naive chase logic: find nearest Prey and move towards it
        # We need access to the environment to find prey, but Agent.step() doesn't receive it in the base definition to prevent cheating.
        # However, for this showcase, we will cheat and attach env to the agent or just pass it if we modify the call loop.
        # Actually, let's use the proper way: The agent should observe.
        # But to keep this demo simple and self-contained without a complex observation loop:
        # We will assume the agent has a 'scan' ability or we modify the loop in the demo.
        # BETTER: The Environment logic can move the agents in `environment_end_of_step` if we wanted centralized AI.
        # OR: We just assume the standard `step(env)` for non-agents, but Agents are special.
        # Let's make them standard Entities for this demo if we want easy cheating, OR just give them a "cheat" reference.
        pass

# Actually, to make this cool and working within the framework:
# We will implement the AI logic inside step(env) by treating them as standard Entities that happen to move.
# The framework distinguishes Agents (no env in step) vs Entities (env in step).
# Let's make them 'SmartEntities' instead of 'Agents' for the sake of simple simulation logic 
# where they have full info.
class SmartEntity(Entity):
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._exposed_actions = []

    @property
    def exposed_actions(self):
        return self._exposed_actions
    
    def move_towards(self, target_pos, env):
        mx, my = self.state.position.x, self.state.position.y
        tx, ty = target_pos.x, target_pos.y
        
        dx = tx - mx
        dy = ty - my
        
        move_action = None
        if abs(dx) > abs(dy):
            move_action = Move_Right() if dx > 0 else Move_Left()
        else:
            move_action = Move_Down() if dy > 0 else Move_Up() # Y is down in many 2D grids, but let's assume standard Cartesian or Matrix?
            # Usually Up is y-1 in matrix, Down is y+1. 
            # Word_Play presets: Move_Up adds (0, 1) -> Cartesian up.
            
        move_action(self, env)

class PredatorEntity(SmartEntity):
    def step(self, env):
        # Find nearest Prey
        preys = [e for e in env.state.entities if isinstance(e, PreyEntity)]
        if not preys: return

        nearest = min(preys, key=lambda p: self.dist(p))
        self.move_towards(nearest.state.position, env)

    def dist(self, other):
        return abs(self.state.position.x - other.state.position.x) + abs(self.state.position.y - other.state.position.y)

class PreyEntity(SmartEntity):
    def step(self, env):
        # Find nearest Predator and flee
        preds = [e for e in env.state.entities if isinstance(e, PredatorEntity)]
        if not preds: 
            # Random move
            actions = [Move_Right(), Move_Left(), Move_Up(), Move_Down()]
            random.choice(actions)(self, env)
            return

        nearest = min(preds, key=lambda p: self.dist(p))
        # Move away: invert target direction roughly
        # Heuristic: move to maximize distance
        candidates = [
            (Move_Right(), 1, 0),
            (Move_Left(), -1, 0),
            (Move_Up(), 0, 1),
            (Move_Down(), 0, -1)
        ]
        best_move = None
        max_dist = -1
        
        start_x, start_y = self.state.position.x, self.state.position.y
        
        for move_action, dx, dy in candidates:
            nx, ny = start_x + dx, start_y + dy
            # Calc dist to pred
            d = abs(nx - nearest.state.position.x) + abs(ny - nearest.state.position.y)
            if d > max_dist:
                max_dist = d
                best_move = move_action
        
        if best_move:
            best_move(self, env)

    def dist(self, other):
        return abs(self.state.position.x - other.state.position.x) + abs(self.state.position.y - other.state.position.y)

class PredatorPreyEnv(Environment):
    def observe(self, agent_id): pass
    def environment_start_of_step(self, actions): pass
    def environment_end_of_step(self, actions): pass
    def _reset(self, seed=None): pass
    
    # We override step to run entity steps since we are likely not passing valid actions for them
    # Actually standard env.step calls entity.step(env) for non-agents automatically.
