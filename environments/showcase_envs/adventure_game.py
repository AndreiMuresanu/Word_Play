from word_play.environment import Environment, Environment_State, Environment_Properties, Entity_State, Entity_Properties, Agent, Entity
from word_play.presets.movement_system_presets import Position_2D, Move_Right, Move_Left, Move_Up, Move_Down, Movement_System

# --- Properties ---
class HeroProperties(Entity_Properties):
    def __init__(self, name="AdvHero"):
        super().__init__(name)
        self.symbol = "H"
        self.color = "CYAN"

class EnemyProperties(Entity_Properties):
    def __init__(self, name="Goblin"):
        super().__init__(name)
        self.symbol = "E"
        self.color = "RED"

class KeyProperties(Entity_Properties):
    def __init__(self, name="Key"):
        super().__init__(name)
        self.symbol = "k"
        self.color = "YELLOW"

class DoorProperties(Entity_Properties):
    def __init__(self, name="Door"):
        super().__init__(name)
        self.symbol = "D"
        self.color = "WHITE"

class WeaponProperties(Entity_Properties):
    def __init__(self, name="Sword"):
        super().__init__(name)
        self.symbol = "/"
        self.color = "CYAN"

class WallProperties(Entity_Properties):
    def __init__(self, name="Wall"):
        super().__init__(name)
        self.symbol = "#"
        self.color = "WHITE"

# --- Entities ---
class Wall(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass
class Key(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Weapon(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Door(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Enemy(Entity):
    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class AdventureHero(Entity):
    def __init__(self, state, properties):
        super().__init__(state, properties)
        self._exposed_actions = []
        self.inventory = [] # List of item names

    @property
    def exposed_actions(self): return self._exposed_actions

    def step(self, env):
        # Move around randomly or towards key/door for showcase
        pass

# --- Environment ---
class AdventureGameEnv(Environment):
    def observe(self, agent_id): pass
    def environment_start_of_step(self, actions): pass
    def environment_end_of_step(self, actions): pass
    def _reset(self, seed=None): pass

    def step(self, action_selections=[]):
        # 1. Custom Movement Validation & Logic
        # We override step to handle interactions BEFORE movement or AS movement happens.
        # But 'movement_system' preset is usually called via action().
        # We can wrap the action execution.
        
        # For this showcase, we'll implement interaction checks when 'movement_is_valid' is called? 
        # No, 'is_valid' is boolean.
        
        # We will iterate entities, find the Hero, and try to move him manually 
        # to effectively simulate 'game logic'.
        
        hero = next((e for e in self.state.entities if isinstance(e, AdventureHero)), None)
        if hero:
            # Simple AI: 
            # 1. If no key, move to Key.
            # 2. If Key, move to Door.
            # 3. If Enemy in way, kill it.
            
            key_in_inv = "Key" in hero.inventory
            target = None
            
            if not key_in_inv:
                # Find key
                k = next((e for e in self.state.entities if isinstance(e, Key)), None)
                if k: target = k.state.position
            else:
                # Find door
                d = next((e for e in self.state.entities if isinstance(e, Door)), None)
                if d: target = d.state.position

            if target:
                mx, my = hero.state.position.x, hero.state.position.y
                tx, ty = target.x, target.y
                
                dx, dy = tx - mx, ty - my
                move_action = None
                
                # Check Horizontal
                if dx != 0:
                    cand_dx = 1 if dx > 0 else -1
                    if self._try_interact(hero, mx + cand_dx, my):
                        hero.state.position.x += cand_dx
                # Check Vertical
                elif dy != 0:
                    cand_dy = 1 if dy > 0 else -1
                    if self._try_interact(hero, mx, my + cand_dy):
                        hero.state.position.y += cand_dy

        # We skip calling super().step() because we manually moved the only active agent
        # But we should call it if we had other dynamics.
        
    def _try_interact(self, hero, x, y):
        # Check what is at x, y
        target_pos = Position_2D(x, y)
        entities_at_target = [e for e in self.state.entities if e.state.position == target_pos]
        
        for e in entities_at_target:
            if isinstance(e, Door):
                if "Key" in hero.inventory:
                    # Unlock! Remove door
                    self.state.entities.remove(e)
                    return True # Can move now (or next turn)
                else:
                    return False # Blocked
            elif isinstance(e, Enemy):
                # Combat!
                # Kill enemy
                self.state.entities.remove(e)
                return True # Move into space
            elif isinstance(e, Key):
                hero.inventory.append("Key")
                self.state.entities.remove(e)
                return True
            elif isinstance(e, Weapon):
                hero.inventory.append("Weapon")
                self.state.entities.remove(e)
                return True
                
        return True # Empty space

def create_adventure_game():
    entities = []
    # Hero
    entities.append(AdventureHero(Entity_State(Position_2D(1, 1)), HeroProperties()))
    
    # Key
    entities.append(Key(Entity_State(Position_2D(5, 1)), KeyProperties()))
    
    # Door (Blocking path to goal?)
    entities.append(Door(Entity_State(Position_2D(3, 3)), DoorProperties()))
    
    # Enemy
    entities.append(Enemy(Entity_State(Position_2D(3, 1)), EnemyProperties()))
    
    # Walls (Explicit Border)
    for x in range(0, 7):
        entities.append(Wall(Entity_State(Position_2D(x, 0)), WallProperties()))
        entities.append(Wall(Entity_State(Position_2D(x, 4)), WallProperties()))
    for y in range(1, 4):
        entities.append(Wall(Entity_State(Position_2D(0, y)), WallProperties()))
        entities.append(Wall(Entity_State(Position_2D(6, y)), WallProperties()))
    
    return AdventureGameEnv(
        state=Environment_State(entities),
        properties=Environment_Properties("Adventure Game"),
        movement_system=Movement_System(Position_2D, [], lambda a,b: False, lambda p,a,e: True), 
        reward_func=lambda *args: [0]
    )
