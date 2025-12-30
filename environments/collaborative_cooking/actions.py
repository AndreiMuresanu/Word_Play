from word_play.environment import Action_On_Other_Entity, Action_On_Self, Entity, Environment
from word_play.presets.movement_system_presets import Position_Oriented_2D

class Interact(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str:
        return "Interact"

    @staticmethod
    def __call__(actor: Entity, env: Environment):
        # 1. Find target in front of actor
        if not hasattr(actor, 'state') or not isinstance(actor.state.position, Position_Oriented_2D):
            return
            
        ox, oy = 0, 0
        o = actor.state.position.orientation % 4
        if o == 0: oy=1 # N
        elif o == 1: ox=1 # E
        elif o == 2: oy=-1 # S
        elif o == 3: ox=-1 # W
        
        tx, ty = actor.state.position.x + ox, actor.state.position.y + oy
        
        # Find blocking entity at tx, ty
        # Prioritize Blocking > Non-Blocking?
        # Usually Interact hits the first relevant thing.
        hits = [e for e in env.state.entities if e.state.position.x == tx and e.state.position.y == ty]
        target = next((e for e in hits if getattr(e.properties, 'blocking', False)), None)
        
        if target and hasattr(target, "on_interact"):
            target.on_interact(actor, env)

class Wait(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Wait."
    @staticmethod
    def __call__(target_entity: Entity, env: Environment): pass

# --- Movement Actions ---

# N(+Y), E(+X), S(-Y), W(-X)
# Orientation 0=N, 1=E, 2=S, 3=W
DELTAS = [(0, 1), (1, 0), (0, -1), (-1, 0)]

def _move(e: Entity, orientation_offset: int = 0, backward: bool = False):
    if not isinstance(e.state.position, Position_Oriented_2D): return
    o = (e.state.position.orientation + orientation_offset) % 4
    dx, dy = DELTAS[o]
    if backward:
        dx, dy = -dx, -dy
    e.state.position.x += dx
    e.state.position.y += dy

class Move_Forward(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Move Forward"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        _move(e)

class Move_Backward(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Move Backward"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        _move(e, backward=True)

class Turn_Left(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Turn Left"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        if not isinstance(e.state.position, Position_Oriented_2D): return
        e.state.position.orientation = (e.state.position.orientation - 1) % 4

class Turn_Right(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Turn Right"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        if not isinstance(e.state.position, Position_Oriented_2D): return
        e.state.position.orientation = (e.state.position.orientation + 1) % 4

class Strafe_Left(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Strafe Left"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        _move(e, orientation_offset=-1)

class Strafe_Right(Action_On_Self):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str: return "Strafe Right"
    @staticmethod
    def __call__(e: Entity, env: Environment):
        _move(e, orientation_offset=1)
