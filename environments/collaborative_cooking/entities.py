from dataclasses import dataclass, field
from typing import List, Optional, Any
from word_play.environment import Entity, Entity_State, Entity_Properties, Action_On_Other_Entity, Environment
from word_play.presets.movement_system_presets import Position_Oriented_2D
from environments.collaborative_cooking.actions import Interact
from environments.collaborative_cooking.agents import Chef
from word_play.renderer import Color

@dataclass
class CookingEntityProperties(Entity_Properties):
    symbol: str = "?"
    color: Any = Color.WHITE
    blocking: bool = False

# --- Interactable Entities ---

# Interact logic is now in actions.py

# --- Specific Entities ---

class ItemEntity(Entity):
    """Represents a physical item on the grid (e.g., on a table)."""
    def __init__(self, position, item_name):
        color = Color.RED if item_name == "Tomato" else Color.WHITE
        symbol = "t" if item_name == "Tomato" else "o"
        if item_name == "Dish": 
            symbol = "d" 
            color = Color.BLUE
            
        props = CookingEntityProperties(name=item_name, symbol=symbol, color=color, blocking=False)
        state = Entity_State(position)
        super().__init__(state, props)
        self.item_name = item_name

    @property
    def exposed_actions(self): return []
    def step(self, env): pass

class Table(Entity):
    """A surface where multiple items can be stacked."""
    def __init__(self, position):
        props = CookingEntityProperties(name="Table", symbol="O", color=Color.YELLOW, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)

    @property
    def exposed_actions(self): return [Interact()]
    def step(self, env): pass

    def on_interact(self, actor: Chef, env: Environment):
        # Place item
        if actor.state.holding is not None:
            # Create physical item
            item_name = actor.state.holding
            # Use COPY of position to avoid reference issues
            pos = Position_Oriented_2D(self.state.position.x, self.state.position.y, 0)
            item = ItemEntity(pos, item_name)
            env.state.entities.append(item)
            actor.state.holding = None
            
        # Pick up item (LIFO behavior or random? Let's pick last added / top)
        elif actor.state.holding is None:
            # Find items at this location
            items_here = [e for e in env.state.entities if isinstance(e, ItemEntity) and 
                          e.state.position.x == self.state.position.x and 
                          e.state.position.y == self.state.position.y]
            
            if items_here:
                # Pick the last one (visually "top")
                item_to_pick = items_here[-1]
                actor.state.holding = item_to_pick.item_name
                env.state.entities.remove(item_to_pick)


class Dispenser(Entity):
    """dispenses an item (Tomato or Plate) to the agent."""
    def __init__(self, position, item_name, symbol, color="MAGENTA"):
        props = CookingEntityProperties(name=f"{item_name}_Dispenser", symbol=symbol, color=color, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
        self.item_name = item_name

    @property
    def exposed_actions(self): return [Interact()]

    def step(self, env): pass

    # We need to hook into the Interact action specific to THIS entity instance
    # But Interact is a class. In Word_Play, the Action is the *Class*.
    # Calls `selection.action(target, actor, env)`.
    # So `Interact(target, actor, env)` is called.
    # We need to implement the logic inside `Interact`.
    # OR, we define specific Action subclasses for each entity type?
    # "Interact" is the shared abstraction.
    # Let's check `Interact.__call__`. It's static. It doesn't know *which* subclass logic to run unless we delegate.
    
    # Better approach: Interact calls `target_entity.interact(actor, env)`
    
# Redefine Interact to delegate
class Interact(Action_On_Other_Entity):
    @staticmethod
    def action_description_text(target_entity: Entity) -> str:
        return f"Interact with {target_entity.properties.name}"

    @staticmethod
    def __call__(target_entity: Entity, actor: Entity, env: Environment):
        if hasattr(target_entity, "on_interact"):
            target_entity.on_interact(actor, env)

# Update entities to have `on_interact`

class Dispenser(Entity):
    def __init__(self, position, item_name, symbol, color=Color.MAGENTA):
        props = CookingEntityProperties(name=f"{item_name}_Dispenser", symbol=symbol, color=color, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
        self.item_name = item_name

    @property
    def exposed_actions(self): return [Interact()]
    def step(self, env): pass

    def on_interact(self, actor: Chef, env: Environment):
        if actor.state.holding is None:
            actor.state.holding = self.item_name
            # print(f"{actor.properties.name} picked up {self.item_name}")

class Counter(Entity):
    def __init__(self, position):
        props = CookingEntityProperties(name="Counter", symbol="X", color=Color.WHITE, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
        self.held_item: Optional[str] = None

    @property
    def exposed_actions(self): return [Interact()]
    def step(self, env): pass

    @property
    def symbol(self): return self.get_symbol()

    def get_symbol(self):
        s = "X"
        if self.held_item == "Tomato": return s + "t"
        if self.held_item == "Plate": return s + "o"
        if self.held_item == "Dish": return s + "d"
        return s

    def on_interact(self, actor: Chef, env: Environment):
        # Pick up
        if actor.state.holding is None and self.held_item is not None:
            actor.state.holding = self.held_item
            self.held_item = None
        # Place
        elif actor.state.holding is not None and self.held_item is None:
            self.held_item = actor.state.holding
            actor.state.holding = None

class Pot(Entity):
    def __init__(self, position):
        props = CookingEntityProperties(name="Pot", symbol="P", color=Color.GREEN, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
        self.ingredients: List[str] = []
        self.cooking_timer: int = 0
        self.status: str = "Empty" # Empty, Cooking, Ready, Plated? No, Ready means Dish is ready.

    @property
    def exposed_actions(self): return [Interact()]

    def step(self, env):
        if self.status == "Cooking":
            self.cooking_timer += 1
            if self.cooking_timer >= 5:
                self.status = "Ready"
                self.cooking_timer = 0

    @property
    def symbol(self): return self.get_symbol()

    def get_symbol(self):
        if self.status == "Empty": return "P"
        if self.status == "Cooking": return "S" # Simmering
        if self.status == "Ready": return "$" # Soup's up
        return "P"
    
    def on_interact(self, actor: Chef, env: Environment):
        # Add Tomato
        if actor.state.holding == "Tomato" and self.status == "Empty":
            self.ingredients.append("Tomato")
            actor.state.holding = None
            if len(self.ingredients) >= 1: # Recipe: 1 Tomato (Simple)
                self.status = "Cooking"
        
        # Plate the Dish
        elif actor.state.holding == "Plate" and self.status == "Ready":
            actor.state.holding = "Dish" # Soup in Plate
            self.status = "Empty"
            self.ingredients = []

class Delivery(Entity):
    def __init__(self, position):
        props = CookingEntityProperties(name="Delivery", symbol="D", color=Color.BLUE, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
        self.total_delivered: int = 0

    @property
    def exposed_actions(self): return [Interact()]
    def step(self, env): pass

    def on_interact(self, actor: Chef, env: Environment):
        if actor.state.holding == "Dish":
            actor.state.holding = None
            self.total_delivered += 1
            # print("Dish Delivered!")


class Wall(Entity):
    def __init__(self, position):
        props = CookingEntityProperties(name="Wall", symbol="#", color=Color.WHITE, blocking=True)
        state = Entity_State(position)
        super().__init__(state, props)
    
    @property
    def exposed_actions(self): return []
    def step(self, env): pass
