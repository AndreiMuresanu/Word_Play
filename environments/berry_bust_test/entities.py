from dataclasses import dataclass
from word_play.environment import Entity, Entity_State, Entity_Properties, Environment
from environments.berry_bust_test.actions import PickBerry, Unlock


@dataclass
class BerryBushProperties(Entity_Properties):
	berry_type: str
	symbol: str = 'B'

@dataclass
class BerryBush_State(Entity_State):
	berry_count: int

class BerryBush(Entity):
	exposed_actions = (PickBerry(), Unlock())
	
	def __init__(self, state: BerryBush_State, properties: BerryBushProperties) -> None:
		super().__init__(state=state, properties=properties)

	def step(self, env: Environment):
		#self.state.berry_count += 1
		pass