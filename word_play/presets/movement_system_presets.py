from dataclasses import dataclass
from word_play.environment import Action_On_Self, Entity, Position, Movement_System, Environment


@dataclass
class Single_Point_Position(Position):
	CONSTANT_POSITION = 0

	def __str__(self):
		return f'{self.CONSTANT_POSITION}'

@dataclass
class Position_1D(Position):
	x: int
	
	def __str__(self):
		return f'{self.x}'

@dataclass
class Position_2D(Position):
	x: int
	y: int
	
	def __str__(self):
		return f'({self.x}, {self.y})'


class Move_Left(Action_On_Self):
	@staticmethod
	def action_description_text(target_entity: Entity) -> str:
		return f'Move left.'

	@staticmethod
	def __call__(target_entity: Entity, env: Environment):
		target_entity.state.position.x -= 1

class Move_Right(Action_On_Self):
	@staticmethod
	def action_description_text(target_entity: Entity) -> str:
		return f'Move right.'

	@staticmethod
	def __call__(target_entity: Entity, env: Environment):
		target_entity.state.position.x += 1

class Move_Up(Action_On_Self):
	@staticmethod
	def action_description_text(target_entity: Entity) -> str:
		return f'Move up.'

	@staticmethod
	def __call__(target_entity: Entity, env: Environment):
		target_entity.state.position.y += 1

class Move_Down(Action_On_Self):
	@staticmethod
	def action_description_text(target_entity: Entity) -> str:
		return f'Move down.'

	@staticmethod
	def __call__(target_entity: Entity, env: Environment):
		target_entity.state.position.y -= 1


def positions_are_close_if_equal(position_A: Position, position_B: Position) -> bool:
	return position_A == position_B

def all_movements_are_valid(postion: Position, movement: Action_On_Self, env: Environment) -> bool:
	return True


# TODO: create movement validations for a bounded 1D region and 2D boxes
#	These might require the addition of a "properties" attribute to the Movement_System class
#	This would contain things like: max_x, min_x, max_y, min_y, etc.
#	Idk if this should be a dict or if it should be typeless (it may be conceivable that you might want a custom class)
#		- i.e., maybe the Movement_System can store the entity positions for fast look-up??? Idk if this is the right place to do that


INFINITE_1D_MOVEMENT_SYSTEM = Movement_System(
	position_type=Position_1D,
	movement_options=(Move_Left(), Move_Right()),
	positions_are_close=positions_are_close_if_equal,
	movement_is_valid=all_movements_are_valid
)

INFINITE_2D_MOVEMENT_SYSTEM = Movement_System(
	position_type=Position_2D,
	movement_options=(Move_Left(), Move_Right(), Move_Up(), Move_Down()),
	positions_are_close=positions_are_close_if_equal,
	movement_is_valid=all_movements_are_valid
)

SINGLE_POINT_MOVEMENT_SYSTEM = Movement_System(
	position_type=Single_Point_Position,
	movement_options=(),
	positions_are_close=positions_are_close_if_equal,
	movement_is_valid=all_movements_are_valid
)