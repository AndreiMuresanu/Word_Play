from typing import List, Optional
from dataclasses import dataclass
from word_play.environment import Environment, Environment_State, Environment_Properties, Action_Selection, Step_Execution_Order, Observation
from word_play.presets.movement_system_presets import ORIENTED_2D_MOVEMENT_SYSTEM, Position_Oriented_2D
from environments.collaborative_cooking.entities import Dispenser, Counter, Pot, Delivery, Wall, CookingEntityProperties, Table, ItemEntity
from environments.collaborative_cooking.agents import Chef, ChefState, FocalAgent, BackgroundAgent
from environments.collaborative_cooking.actions import Interact

@dataclass
class CollaborativeCookingObservation(Observation):
    grid: List[List[str]]
    inventory: Optional[str]
    possible_actions: List[Action_Selection]

    def __str__(self):
        return f"Grid({len(self.grid)}x{len(self.grid[0])}), Holding: {self.inventory}"

class CollaborativeCookingEnv(Environment):
    def __init__(self, layout_str: str, num_focal_agents: int = 1, num_background_agents: int = 0):
        self.layout_str = layout_str.strip()
        entities = self._parse_layout(self.layout_str, num_focal_agents, num_background_agents)
        
        state = Environment_State(entities=entities)
        props = Environment_Properties(description="Robust Collaborative Cooking")
        
        # Reward Tracking
        self.delivery_stations = [e for e in entities if isinstance(e, Delivery)]
        self.previous_total = 0

        # Define reward function
        def reward_func(actions, env):
            current_total = sum(d.total_delivered for d in env.delivery_stations)
            diff = current_total - env.previous_total
            env.previous_total = current_total
            return [float(diff)] * len(env.agents)

        super().__init__(
            state=state,
            properties=props,
            movement_system=ORIENTED_2D_MOVEMENT_SYSTEM,
            reward_func=reward_func,
            step_execution_order=Step_Execution_Order.Agents_First
        )

    def _parse_layout(self, layout: str, n_focal: int, n_bg: int):
        rows = layout.split('\n')
        # Filter empty rows if any
        rows = [r for r in rows if len(r.strip()) > 0]
        rows = list(reversed(rows)) # Y=0 at bottom
        
        entities = []
        agent_idx = 0
        total_agents = n_focal + n_bg
        
        for y, row in enumerate(rows):
            for x, char in enumerate(row):
                pos = Position_Oriented_2D(x, y, 0)
                if char == '#': entities.append(Wall(pos))
                elif char == 'O': entities.append(Table(pos))
                elif char == 'T': entities.append(Dispenser(pos, "Tomato", "T", "RED"))
                elif char == 'L': entities.append(Dispenser(pos, "Plate", "L", "WHITE"))
                elif char == 'P': entities.append(Pot(pos))
                elif char == 'C': entities.append(Counter(pos))
                elif char == 'D': entities.append(Delivery(pos))
                elif char == 'S':
                    if agent_idx < total_agents:
                        color = "CYAN" if agent_idx < n_focal else "MAGENTA"
                        name = f"InfoChef_{agent_idx}" if agent_idx < n_focal else f"BgChef_{agent_idx}"
                        
                        kwargs = {
                            "state": ChefState(Position_Oriented_2D(x, y, 0)),
                            "properties": CookingEntityProperties(name=name, symbol="A", color=color, blocking=True)
                        }
                        
                        if agent_idx < n_focal:
                            agent = FocalAgent(**kwargs)
                        else:
                            agent = BackgroundAgent(**kwargs)
                            agent.role = "chopper" if agent_idx % 2 == 0 else "deliverer"
                            
                        entities.append(agent)
                        agent_idx += 1
        return entities

    def step(self, action_selections: List[Action_Selection]) -> None:
        """
        Custom step logic to handle Collision Detection and Interactions.
        This overrides the standard Environment.step to ensure robust mechanics.
        """
        
        # 2. Resolve Intent vs Collision
        # Snapshot current positions
        occupied = { (e.state.position.x, e.state.position.y) for e in self.state.entities if getattr(e.properties, 'blocking', False) }
        
        # Filter movement actions
        moves = []
        others = []
        for selection in action_selections:
            # Check if action is movement (Move_*, Strafe_*)
            # We can check class name or type
            aname = type(selection.action).__name__
            if "Move" in aname or "Strafe" in aname:
                moves.append(selection)
            else:
                others.append(selection)
        
        # Execution of non-movement (Turns, Interactions, Waits)
        for selection in others:
            # All non-movement actions are now Action_On_Self (Turn, Wait, Interact)
            # Interact is now self-contained, finding its own target.
            selection.action(selection.target_entity, self)

        # Execution of Movement with Collision Checking
        # Simple resolution: Serial execution. If move hits blockage, fail. 
        # Better: Simultaneous? Serial is easier and robust enough for basic Overcooked.
        
        for selection in moves:
            actor = selection.target_entity 
            old_x, old_y = actor.state.position.x, actor.state.position.y
            
            # Apply (mutation)
            selection.action(actor, self)
            
            new_x, new_y = actor.state.position.x, actor.state.position.y

            collision = False
            if (new_x, new_y) in occupied and (new_x, new_y) != (old_x, old_y):
                 collision = True
            
            if collision:
                # Revert
                actor.state.position.x = old_x
                actor.state.position.y = old_y
            else:
                # Success - Update occupied set for subsequent movers (serial)
                occupied.remove((old_x, old_y))
                occupied.add((new_x, new_y))

        # 3. Environment Entity Updates (Cooking timers etc)
        for e in self.state.entities:
            if hasattr(e, 'step'):
                e.step(self)
        
        # 4. Calculate Rewards
        self.last_rewards = self.reward_func(action_selections, self)

    def observe(self, agent_id: int) -> Observation:
        agent = self.agents[agent_id]
        # Generate 11x11 grid centered on agent
        center_x = agent.state.position.x
        center_y = agent.state.position.y
        
        grid = []
        for dy in range(5, -6, -1): # 5 to -5
            row_str = []
            for dx in range(-5, 6): # -5 to 5
                target_x = center_x + dx
                target_y = center_y + dy
                
                # Check bounds/entities
                symbol = "."
                for e in self.state.entities:
                    if hasattr(e.state.position, 'x') and e.state.position.x == target_x and e.state.position.y == target_y:
                        if hasattr(e, 'get_symbol'):
                            symbol = e.get_symbol()
                        elif hasattr(e.properties, 'symbol'):
                            symbol = e.properties.symbol
                        break
                row_str.append(symbol)
            grid.append(row_str)
        return CollaborativeCookingObservation(
            grid=grid, 
            inventory=getattr(agent.state, 'holding', None),
            possible_actions=self.get_possible_actions(agent_id)
        )

    def environment_start_of_step(self, action_selections): pass
    def environment_end_of_step(self, action_selections): pass
    def _reset(self, seed=None): pass

    def _find_actor(self, selection):
        # Helper if selection structure is ambiguous
        return selection.target_entity 


# We need to implement the Interact Logic inside the Interact class in `entities.py` calling back to Env?
# Or we monkey-patch/implement `__call__` in entities.
# Actually, I defined `Interact` in `entities.py` but left it empty.
# I should update `entities.py` to have the real interaction logic, OR
# put the logic in `env.py` and have `Interact` call it. 
# Implementing in `Interact.__call__` is cleaner if it has access to everything.

