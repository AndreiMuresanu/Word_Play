from dataclasses import dataclass, field
from typing import Optional, List, Dict
from word_play.environment import Entity, Entity_State, Entity_Properties, Agent, Action_Selection, Observation
from word_play.presets.movement_system_presets import Position_Oriented_2D
from collections import deque
from environments.collaborative_cooking.actions import Wait, Move_Forward, Turn_Left, Turn_Right, Interact

@dataclass
class ChefState(Entity_State):
    holding: Optional[str] = None # e.g., "Tomato", "Plate", "Dish"

class Chef(Agent):
    """Base class for all cooking agents."""
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._actions_on_self = [] 
        self.role: str = "general" # e.g. "chopper", "deliverer"

    @property
    def exposed_actions(self): return []

    @property
    def actions_on_self(self): return self._actions_on_self

    @actions_on_self.setter
    def actions_on_self(self, value): self._actions_on_self = list(value)
    
    def step(self, env=None): pass

    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        # Abstract
        return None, {}

    # Custom helper for rendering orientation
    @property
    def symbol(self):
        if not isinstance(self.state.position, Position_Oriented_2D):
            return "A"
        orientation = self.state.position.orientation % 4
        # 0:N(^), 1:E(>), 2:S(v), 3:W(<)
        sym = "A"
        if orientation == 0: sym = "^"
        elif orientation == 1: sym = ">"
        elif orientation == 2: sym = "v"
        elif orientation == 3: sym = "<"
        
        if self.state.holding:
            h = self.state.holding
            c = "?"
            if h == "Tomato": c = "t"
            elif h == "Plate": c = "o"
            elif h == "Dish": c = "@"
            elif h == "Soup": c = "s"
            return sym + c
        return sym

class CookingAgent(Chef): 
    pass

class FocalAgent(Chef):
    """An agent that is evaluated (controlled by external policy or user)."""
    def __init__(self, state, properties):
        super().__init__(state, properties)
        # Identify visually
        # properties.color should be set by Env
        pass
    
    # select_action remains abstract or passes through

class BackgroundAgent(Chef):
    """A fixed-policy agent (NPC) that performs a specific role."""
    def __init__(self, state, properties, policy_fn=None):
        super().__init__(state, properties)
        self.policy_fn = policy_fn
    
    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:
        if self.policy_fn:
            return self.policy_fn(self, observation)
        # Default fallback: Random or Wait
        return Action_Selection(Wait(), self), {}

class HeuristicChef(Chef):
    """
    A simple heuristic agent that moves towards a target character in the observation grid.
    Logic:
    1. Scan observation grid for target_char.
    2. BFS to find shortest path.
    3. Return action to move/turn towards next step.
    4. If adjacent and facing, Interact.
    """
    def __init__(self, state, properties, targets: List[str] = None):
        super().__init__(state, properties)
        self.targets = targets if targets else [] # List of symbols to look for, in priority
        self.current_goal_index = 0
        
    def select_action(self, observation: Observation) -> tuple[Action_Selection, dict]:

        if not self.targets: return Action_Selection(Wait(), self), {}
        
        # Determine Current Target based on holding state
        # Simple State Machine for Demo:
        # If holding nothing -> limit targets to Dispensers/Counters
        # If holding Tomato -> limit targets to Pot/Counter
        # But for now, let's just use the targets list provided in init or cycled external?
        # Actually, let's just seek the first found target from the list.
        
        target_char = self.targets[self.current_goal_index % len(self.targets)]
        
        # Grid is in observation.grid (List[List[str]])
        # Center is agent. 
        # Grid size is 11x11, center is (5,5).
        grid = observation.grid
        center = (5, 5)
        
        # Helper: Find all occurrences of target_char
        goals = []
        for y, row in enumerate(grid):
            for x, char in enumerate(row):
                # Check rough match (e.g. "T" or "Xt" contains "t"?)
                # Exact match for now
                if target_char in char: 
                    goals.append((x, y))
                    
        if not goals:
            # If target isn't found, just Wait. Spinning is confusing.
            return Action_Selection(Wait(), self), {}
            
        # BFS
        q = deque([(center, [])]) # (pos, path_of_actions)
        visited = {center}
        
        # Determine current orientation from observation? 
        # Observation doesn't give orientation directly, but we are the agent, we know our state?
        # Agent.step() doesn't pass env, but Agent instance has self.state.
        
        # Simulating movement in Grid relative to (5,5).
        # We need to know which way we are facing to know what "Move_Forward" does relative to (x,y).
        # We assume the grid is aligned with global N/E/S/W? 
        # "Generate 11x11 grid centered on agent".
        # If grid is absolute orientation (which observation usually is), then (0,0) is bottom-left?
        # obs grid: row 0 is y+5, row 10 is y-5. 
        # Let's map strict coords: observation.grid[row][col]
        # row 0 = Top (y+5 relative or absolute? The observe function loop: dy from 5 down to -5).
        # So row 0 is y_agent + 5. row 10 is y_agent - 5.
        # col 0 is x_agent - 5. col 10 is x_agent + 5.
        
        # We need self.state.position.orientation to know our Forward.
        # Orientation: 0=N(+y), 1=E(+x), 2=S(-y), 3=W(-x).
        
        # Heuristic: just move to adjacent cell of goal.
        # But we need pathfinding because walls.
        
        # Simplified: Just return Move/Turn towards first goal found.
        gx, gy = goals[0] # Target Grid Coords (col, row)
        
        # row index in grid corresponds to Y. col to X.
        # center is grid[5][5].
        # Target (x, y) relative to grid top-left being (0,0).
        
        # My pos in grid indices: (5, 5).
        # Goal pos in grid indices: (gy, gx) wait. enumerate(row) -> x is col index.
        # goals stores (col_idx, row_idx).
        
        cx, cy = 5, 5
        tx, ty = gx, gy
        
        # Delta
        dx = tx - cx
        dy = ty - cy # note: row index increases DOWN. Y increases UP.
        # Actually observation loop: row 0 is Y+5.
        # So higher row index = Lower Y.
        # dy in grid rows: ty - cy.
        # If ty > cy (target is lower in grid rows), it means target has LOWER Y.
        # So real world Y difference: -(ty - cy).
        
        world_dx = dx
        world_dy = -dy
        
        # Are we adjacent?
        dist = abs(world_dx) + abs(world_dy)
        if dist == 1:
            # Check orientation
            o = self.state.position.orientation % 4
            # N(0) -> dy=+1. E(1) -> dx=+1. S(2) -> dy=-1. W(3) -> dx=-1.
            
            desired_o = -1
            if world_dy == 1: desired_o = 0
            elif world_dx == 1: desired_o = 1
            elif world_dy == -1: desired_o = 2
            elif world_dx == -1: desired_o = 3
            
            if o == desired_o:
                return Action_Selection(Interact(), self), {}
            else:
                # Turn efficiently
                diff = (desired_o - o) % 4
                if diff == 1: return Action_Selection(Turn_Right(), self), {}
                else: return Action_Selection(Turn_Left(), self), {}
                
        # Move towards
        # If we need to move +X: Face East, Move.
        # If we need to move -X: Face West, Move.
        # If we need to move +Y: Face North, Move.
        # If we need to move -Y: Face South, Move.
        
        # Prioritize axis with larger delta?
        target_o = 0
        if abs(world_dx) > abs(world_dy):
             target_o = 1 if world_dx > 0 else 3
        else:
             target_o = 0 if world_dy > 0 else 2
             
        curr_o = self.state.position.orientation % 4
        
        if curr_o == target_o:
            return Action_Selection(Move_Forward(), self), {}
        else:
            # Turn
            diff = (target_o - curr_o) % 4
            if diff == 1: return Action_Selection(Turn_Right(), self), {}
            else: return Action_Selection(Turn_Left(), self), {}


