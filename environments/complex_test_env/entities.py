from dataclasses import dataclass
from word_play.environment import Entity, Entity_State, Entity_Properties, Environment, Action_On_Self, Observation, Action_Selection
from word_play.presets.movement_system_presets import Move_Up, Move_Down, Move_Left, Move_Right
import random

@dataclass
class SimpleEntityProperties(Entity_Properties):
    symbol: str
    color: str = 'WHITE'

@dataclass
class SmartAgentProperties(Entity_Properties):
    symbol: str = 'A'
    color: str = 'GREEN'

class SmartAgent(Entity):
    def __init__(self, state: Entity_State, properties: SmartAgentProperties) -> None:
        super().__init__(state=state, properties=properties)
        self.actions_on_self = (Move_Up(), Move_Down(), Move_Left(), Move_Right())
    
    @property
    def exposed_actions(self):
        return ()

    def step(self, env: Environment):
        # Allow agent access to environment here for simple logic (auto-move)
        # In this test env, agents move randomly on their own step
        pass
    
    # We fake being an Agent class for the renderer detection
    is_agent = True

class Obstacle(Entity):
    @property
    def exposed_actions(self):
        return ()
    def step(self, env: Environment):
        pass

class Gold(Entity):
    @property
    def exposed_actions(self):
        return ()
    def step(self, env: Environment):
        pass

class Trap(Entity):
    @property
    def exposed_actions(self):
        return ()
    def step(self, env: Environment):
        pass
