import random
from word_play.environment import Environment, Environment_State, Environment_Properties, Entity_State, Entity_Properties, Agent, Entity
from word_play.presets.movement_system_presets import INFINITE_2D_MOVEMENT_SYSTEM, Position_2D, Move_Right, Move_Left, Move_Up, Move_Down

class Resource(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Gatherer(Entity):
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._exposed_actions = []

    @property
    def exposed_actions(self): return self._exposed_actions
    
    def step(self, env):
        # Random movement
        moves = [Move_Right(), Move_Left(), Move_Up(), Move_Down()]
        random.choice(moves)(self, env)

class ResourceGatheringEnv(Environment):
    def observe(self, agent_id): pass
    
    def environment_start_of_step(self, actions):
        # Spawn resource with 10% chance
        if random.random() < 0.10:
            x, y = random.randint(1, 8), random.randint(1, 8)
            # Simple check to avoid stacking on agents? Nah, let it stack.
            r_props = Entity_Properties(name="Resource")
            r_props.symbol = "*"
            r_props.color = "MAGENTA"
            
            res = Resource(Entity_State(Position_2D(x, y)), r_props)
            self.state.entities.append(res)

    def environment_end_of_step(self, actions):
        # Consumption logic: if Gatherer is on Resource, remove Resource
        # We need to find overlaps
        gatherers = [e for e in self.state.entities if isinstance(e, Gatherer)]
        resources = [e for e in self.state.entities if isinstance(e, Resource)]
        
        to_remove = []
        for r in resources:
            for g in gatherers:
                if r.state.position.x == g.state.position.x and r.state.position.y == g.state.position.y:
                    to_remove.append(r)
                    break 
        
        for r in to_remove:
            if r in self.state.entities:
                self.state.entities.remove(r)

    def _reset(self, seed=None): pass
    
    # We don't need to override step anymore since Gatherer is an Entity
    # def step(self, action_selections=[]):
    #     super().step(action_selections)
