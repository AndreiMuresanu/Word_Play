"""
Simplified PixelRenderer - Clean rewrite for reliability
"""
import pygame
import os
import sys
from typing import Optional, Tuple

class SpriteManager:
    """Manages sprite loading and mapping"""
    def __init__(self):
        self.sprites = {}  # name -> surface
        self.mappings = {}  # symbol/name -> sprite_name
        
    def register_sprite(self, name: str, path: str, rect: Optional[Tuple[int, int, int, int]] = None):
        """Load and register a sprite"""
        try:
            img = pygame.image.load(path).convert_alpha()
            if rect:
                x, y, w, h = rect
                img = img.subsurface((x, y, w, h))
            self.sprites[name] = img
            print(f"Loaded {path} ({img.get_width()}x{img.get_height()})")
        except Exception as e:
            print(f"Failed to load {path}: {e}")
            
    def register_mapping(self, key: str, sprite_name: str):
        """Map a symbol/name to a sprite"""
        self.mappings[key] = sprite_name
        
    def get_tile(self, name: str, fallback: str = None):
        """Get sprite by name or mapping"""
        # Try direct name
        if name in self.sprites:
            return self.sprites[name]
        # Try mapping
        if name in self.mappings:
            mapped = self.mappings[name]
            if mapped in self.sprites:
                return self.sprites[mapped]
        # Try fallback
        if fallback and fallback in self.mappings:
            mapped = self.mappings[fallback]
            if mapped in self.sprites:
                return self.sprites[mapped]
        return None


class PixelRenderer:
    """Simple, reliable pixel renderer"""
    def __init__(self, env, tile_size=32, window_size=(800, 600)):
        self.env = env
        self.tile_size = tile_size
        self.window_w, self.window_h = window_size
        self.screen = None
        self.sprite_manager = SpriteManager()
        
    def init_window(self):
        """Initialize pygame window"""
        # macOS fix
        if sys.platform == 'darwin':
            os.environ['SDL_VIDEO_WINDOW_POS'] = '100,100'
            
        pygame.init()
        self.screen = pygame.display.set_mode(
            (self.window_w, self.window_h),
            pygame.RESIZABLE | pygame.SHOWN
        )
        pygame.display.set_caption("Word Play - Pixel Renderer")
        
    def render(self):
        """Render the environment"""
        if not self.screen:
            self.init_window()
            
        # Calculate grid size
        max_x = max_y = 0
        for e in self.env.state.entities:
            if hasattr(e.state.position, 'x'):
                max_x = max(max_x, e.state.position.x)
            if hasattr(e.state.position, 'y'):
                max_y = max(max_y, e.state.position.y)
                
        grid_w = max_x + 1
        grid_h = max_y + 1
        
        # Create canvas
        canvas_w = grid_w * self.tile_size
        canvas_h = grid_h * self.tile_size
        canvas = pygame.Surface((canvas_w, canvas_h))
        
        # Draw floor background
        floor_sprite = self.sprite_manager.get_tile('Floor', '.')
        if floor_sprite:
            floor_scaled = pygame.transform.scale(floor_sprite, (self.tile_size, self.tile_size))
            for y in range(grid_h):
                for x in range(grid_w):
                    canvas.blit(floor_scaled, (x * self.tile_size, y * self.tile_size))
        else:
            canvas.fill((100, 100, 100))  # Gray if no floor
            
        # Draw entities (sorted by layer)
        # Group agents by tile for sub-grid rendering
        agent_groups = {} # (x,y) -> [agents]
        bg_entities = []
        
        for entity in self.env.state.entities:
            layer = self._get_layer(entity)
            if layer >= 10: # Agents
                pos = entity.state.position
                key = (getattr(pos, 'x', 0), getattr(pos, 'y', 0))
                if key not in agent_groups: agent_groups[key] = []
                agent_groups[key].append(entity)
            else:
                bg_entities.append(entity)
                
        # Sort background entities
        bg_entities.sort(key=self._get_layer)
        
        # 1. Draw Background Entities (Walls, Counters, Items)
        for entity in bg_entities:
            pos = entity.state.position
            x = getattr(pos, 'x', 0)
            y = getattr(pos, 'y', 0)
            
            # Flip Y
            screen_y = grid_h - 1 - y
            px = x * self.tile_size
            py = screen_y * self.tile_size
            
            # Get sprite
            name = getattr(entity.properties, 'name', '?')
            symbol = getattr(entity, 'symbol', '?')
            
            if name == 'Floor' or symbol == '.': continue
            
            sprite = self._get_entity_sprite(entity)
            if sprite:
                scaled = pygame.transform.scale(sprite, (self.tile_size, self.tile_size))
                canvas.blit(scaled, (px, py))
                
                # Check for held item (Counter/Table)
                # Some entities like Counter store item in 'held_item' string or 'held_item' property
                held_item = getattr(entity, 'held_item', None)
                if held_item and isinstance(held_item, str):
                    item_sprite = self.sprite_manager.get_tile(held_item, held_item)
                    if item_sprite:
                        # Draw item centered on counter
                        # Scale slightly smaller than full tile (e.g. 70%)
                        i_size = int(self.tile_size * 0.7)
                        i_scaled = pygame.transform.scale(item_sprite, (i_size, i_size))
                        
                        ix = px + (self.tile_size - i_size) // 2
                        iy = py + (self.tile_size - i_size) // 2
                        
                        canvas.blit(i_scaled, (ix, iy))

        # 2. Draw Agents (Sub-grid for stacking)
        # Sort groups by Y to ensure front-to-back ordering (Painter's Algorithm)
        # Higher Grid Y = Top of Screen (if grid 0,0 is bottom-left). 
        # Actually screen_y = grid_h - 1 - y. 
        # Smaller screen_y = Top. Large screen_y = Bottom.
        # We want small screen_y drawn FIRST (behind), Large screen_y drawn LAST (front).
        sorted_keys = sorted(agent_groups.keys(), key=lambda k: (grid_h - 1 - k[1]))
        
        for (ax, ay) in sorted_keys:
            group = agent_groups[(ax, ay)]
            count = len(group)
            
            screen_y = grid_h - 1 - ay
            base_px = ax * self.tile_size
            base_py = screen_y * self.tile_size
            
            if count == 1:
                # Single Agent - Center
                self._render_agent(canvas, group[0], base_px, base_py, self.tile_size)
            else:
                # Stacked - 2x2 Subgrid
                sub_size = self.tile_size // 2
                offsets = [(0, 0), (sub_size, 0), (0, sub_size), (sub_size, sub_size)]
                
                for i, agent in enumerate(group[:4]):
                    ox, oy = offsets[i]
                    self._render_agent(canvas, agent, base_px + ox, base_py + oy, sub_size)
                    
        self._finalize_render(canvas, canvas_w, canvas_h)

    def _render_agent(self, canvas, agent, px, py, slot_size):
        """Helper to render one agent and its held item"""
        sprite = self._get_entity_sprite(agent)
        visual_size = int(self.tile_size * 1.5) # Always use consistent large size
        
        # Center horizontally in the slot, align bottom of sprite to bottom of slot
        off_x = (slot_size - visual_size) // 2
        off_y = (slot_size - visual_size)
        
        if sprite:
            scaled = pygame.transform.scale(sprite, (visual_size, visual_size))
            canvas.blit(scaled, (px + off_x, py + off_y))
            
        # Draw Held Item
        holding = getattr(agent.state, 'holding', None)
        if holding:
            item_sprite = self.sprite_manager.get_tile(holding, holding)
            if item_sprite:
                # Item size relative to the visual agent size, roughly head size
                i_size = int(visual_size * 0.5) 
                i_scaled = pygame.transform.scale(item_sprite, (i_size, i_size))
                
                # Center horizontally relative to slot (same as agent)
                ix = px + (slot_size - i_size) // 2
                
                # Position at "Chest Level" (overlapping body) to keep it "on the same tile"
                # Visual Top = py + off_y
                # Visual Height = visual_size
                # We want item roughly in the middle-bottom of the visual sprite
                # Let's say 40% down from top
                
                visual_top = py + off_y
                iy = visual_top + int(visual_size * 0.4) # Chest/Hands level
                
                # Ensure it doesn't go too low? 
                # If visual_size=48, item=24. top+24. Item ends at top+48 (feet).
                # This aligns item bottom with agent feet. Looks like carrying low.
                
                canvas.blit(i_scaled, (ix, iy))
                
    def _finalize_render(self, canvas, canvas_w, canvas_h):
        # Scale canvas to fit window
        scale = min(self.window_w / canvas_w, self.window_h / canvas_h) * 0.9
        display_w = int(canvas_w * scale)
        display_h = int(canvas_h * scale)
        scaled_canvas = pygame.transform.scale(canvas, (display_w, display_h))
        
        # Center on screen
        offset_x = (self.window_w - display_w) // 2
        offset_y = (self.window_h - display_h) // 2
        
        # Draw to screen
        self.screen.fill((30, 30, 30))
        self.screen.blit(scaled_canvas, (offset_x, offset_y))
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                self.window_w = event.w
                self.window_h = event.h
                self.screen = pygame.display.set_mode((self.window_w, self.window_h), pygame.RESIZABLE)
                
        pygame.display.flip()
        
    def _get_layer(self, entity):
        """Get rendering layer for entity"""
        name = getattr(entity.properties, 'name', '')
        symbol = getattr(entity, 'symbol', '?')
        
        if 'Floor' in name or symbol == '.':
            return 0
        if 'Wall' in name or symbol == '#':
            return 1
        if 'Counter' in name or 'Pot' in name:
            return 2
        if 'Chef' in name or symbol in ['^', '>', 'v', '<', 'A']:
            return 10
        return 5
        
    def _get_entity_sprite(self, entity):
        """Get sprite for an entity"""
        name = getattr(entity.properties, 'name', '?')
        symbol = getattr(entity, 'symbol', '?')
        
        # Try name first
        sprite = self.sprite_manager.get_tile(name)
        if sprite:
            return sprite
            
        # Try symbol (Dynamic)
        sprite = self.sprite_manager.get_tile(symbol)
        if sprite: return sprite
        
        # Try properties symbol (Static)
        prop_symbol = getattr(entity.properties, 'symbol', None)
        if prop_symbol:
            sprite = self.sprite_manager.get_tile(prop_symbol)
            if sprite: return sprite
            
        # Try dispenser mapping
        if 'Dispenser' in name:
            parts = name.split('_')
            if len(parts) >= 2:
                item = parts[1]
                sprite = self.sprite_manager.get_tile(item)
                if sprite:
                    return sprite
                    
        return None


def setup_default_assets(sprite_manager: SpriteManager):
    """Load default DawnLike + Food + Character assets"""
    print("--- Loading Default Assets (DawnLike, FreePixelFood & Mana Seed) ---")
    sm = sprite_manager
    
    # --- CONSTANTS ---
    CHAR_SIZE = 64
    ENV_SIZE = 16
    
    # Character Animation Offsets (Row Indices)
    # Mana Seed Logic: 0=Up, 1=Left, 2=Down, 3=Right (for this basic sheet)
    # Actually based on visual check:
    # Row 0: Up
    # Row 1: Left 
    # Row 2: Down
    # Row 3: Right
    CHAR_DIRECTIONS = {
        'Up': 0, 
        'Left': 1, 
        'Down': 2, 
        'Right': 3
    }
    
    # --- PATHS ---
    BASE_LIB = "sprite_library"
    PATH_DAWNLIKE = os.path.join(BASE_LIB, "DawnLike")
    PATH_FOOD = os.path.join(BASE_LIB, "FreePixelFood", "Assets", "FreePixelFood", "Sprite", "Food")
    PATH_CHARS = os.path.join(BASE_LIB, "FREE Mana Seed Character Base Demo 2.0", "char_a_p1")
    
    # --- HELPER FUNCTIONS ---
    def register_env_tile(name, filename, mapping_chars=None):
        path = os.path.join(PATH_DAWNLIKE, filename)
        sm.register_sprite(name, path)
        if mapping_chars:
            if isinstance(mapping_chars, str):
                sm.register_mapping(mapping_chars, name)
            else:
                for char in mapping_chars:
                    sm.register_mapping(char, name)
                    
    def register_food_item(name, filename, mapping_char=None):
        path = os.path.join(PATH_FOOD, filename)
        sm.register_sprite(name, path)
        if mapping_char:
            sm.register_mapping(mapping_char, name)
            
    def register_character(base_name, filename):
        path = os.path.join(PATH_CHARS, filename)
        
        # Register directional sprites
        for direction, row_idx in CHAR_DIRECTIONS.items():
            sprite_name = f"{base_name}_{direction}"
            rect = (0, row_idx * CHAR_SIZE, CHAR_SIZE, CHAR_SIZE)
            sm.register_sprite(sprite_name, path, rect)
            
        # Default Mappings
        sm.register_mapping(base_name, f"{base_name}_Down") # Default to Down
        
    # --- 1. ENVIRONMENT (DawnLike) ---
    register_env_tile('Floor', "day stone floor c.png", '.')
    register_env_tile('Wall', "dim brick wall center.png", '#')
    register_env_tile('Counter', "yes box_0.png", ['X', 'C'])
    register_env_tile('Delivery', "magic portal tile.png", ['D', 'S'])
    
    # --- 2. ITEMS (FreePixelFood) ---
    register_food_item('Tomato', "Tomato.png", 'T')
    register_food_item('Pot', "Honey.png", 'P')
    register_food_item('Plate', "Tart.png", 'L')
    register_food_item('Dish', "Jam.png")
    
    # --- 3. CHARACTERS (Mana Seed) ---
    register_character('Chef', "char_a_p1_0bas_humn_v00.png")
    
    # --- 4. ADDITIONAL MAPPINGS ---
    # Map symbols to specific directional sprites if needed
    sm.register_mapping('A', 'Chef_Down')
    sm.register_mapping('^', 'Chef_Up')
    sm.register_mapping('v', 'Chef_Down')
    sm.register_mapping('<', 'Chef_Left')
    sm.register_mapping('>', 'Chef_Right')
