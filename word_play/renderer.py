import os
import time
from typing import Optional
from word_play.environment import Environment, Entity, Position
from word_play.presets.movement_system_presets import Position_2D, Position_1D

class AsciiRenderer:
    """
    A dynamic ASCII renderer for environments.
    """
    # ANSI Color Codes
    COLORS = {
        'RED': '\033[91m',
        'GREEN': '\033[92m',
        'YELLOW': '\033[93m',
        'BLUE': '\033[94m',
        'MAGENTA': '\033[95m',
        'CYAN': '\033[96m',
        'WHITE': '\033[97m',
        'RESET': '\033[0m'
    }

    def __init__(self, env: Environment, refresh_rate: float = 0.1):
        self.env = env
        self.refresh_rate = refresh_rate

    def _colorize(self, text: str, color: str) -> str:
        code = self.COLORS.get(color.upper(), self.COLORS['RESET'])
        return f"{code}{text}{self.COLORS['RESET']}"

    def _get_entity_color(self, entity: Entity) -> str:
        # Check explicit color property
        if hasattr(entity, 'color'):
             return entity.color
        if hasattr(entity, 'properties') and hasattr(entity.properties, 'color'):
             return entity.properties.color
        
        # Default colors based on type
        if hasattr(entity, 'actions_on_self') or getattr(entity, 'is_agent', False) or 'Agent' in entity.__class__.__name__:
            return 'GREEN'
        name_lower = getattr(entity.properties, 'name', '').lower()
        if 'gold' in name_lower or 'treasure' in name_lower:
            return 'YELLOW'
        if 'trap' in name_lower or 'lava' in name_lower or 'enemy' in name_lower:
            return 'RED'
        if 'obstacle' in name_lower or 'wall' in name_lower:
            return 'WHITE'
        
        return 'RESET'

    def render(self, clear: bool = True, return_string: bool = False, show_legend: bool = True, label: Optional[str] = None, envs: list = None, number_of_environments: Optional[int] = None) -> Optional[str]:
        """
        Renders the current state of the environment.
        :param clear: If True, clears the console before printing. (Ignored if return_string is True)
        :param return_string: If True, returns the rendered string instead of printing it.
        :param show_legend: If True, appends the legend to the output.
        :param label: If provided, overrides the environment description in the header.
        :param envs: List of environments to render in vector mode.
        :param number_of_environments: Max number of environments to render in vector mode.
        """
        if envs is not None:
             # Delegate to Vector Renderer
             vector_renderer = VectorAsciiRenderer(envs)
             return vector_renderer.render(count=number_of_environments, clear=clear, show_legend=show_legend, return_string=return_string)

        buffer = []
        
        def out(s):
            buffer.append(str(s))
            
        # Header
        header_text = f"Environment {label}" if label else f"Environment: {self.env.properties.description}"
        out(header_text)
        
        # Determine render based on position type
        if isinstance(self.env.movement_system.position_type, type(Position_2D)) or self.env.movement_system.position_type == Position_2D:
            self._render_2d(out)
        else:
             self._render_generic(out)

        # Render Legend
        if show_legend:
            self._render_legend(out)
        
        if hasattr(self.env, 'last_rewards') and self.env.last_rewards:
            rewards = [r for r in self.env.last_rewards if r is not None]
            if rewards:
                 out(f"Last Rewards: {rewards}")
        
        rendered_str = "\n".join(buffer)
        
        if return_string:
            return rendered_str
        
        if clear:
             os.system('cls' if os.name == 'nt' else 'clear')
        print(rendered_str)

    def _render_legend(self, out_func, entities=None):
        """
        Renders a dynamic legend.
        """
        if entities is None:
            entities = self.env.state.entities

        unique_entities = {} 
        for entity in entities:
            sym = self._get_symbol(entity)
            col = self._get_entity_color(entity)
            name = getattr(entity.properties, 'name', 'Unknown')
            key = (sym, col)
            if key not in unique_entities:
                unique_entities[key] = name
        
        unique_entities[('+', 'MAGENTA')] = 'Stacked Agents'
        
        out_func("Legend:")
        legend_items = []
        for (sym, col), name in unique_entities.items():
            colored_sym = self._colorize(sym, col)
            legend_items.append(f"[{colored_sym}] {name}")
        
        chunk_size = 3
        for i in range(0, len(legend_items), chunk_size):
            out_func("   ".join(legend_items[i:i+chunk_size]))
        out_func("")

    def _render_2d(self, out_func):
        """
        Renders entities on a 2D grid.
        Handles stacking of entities.
        """
        entities = self.env.state.entities
        if not entities:
            out_func("[Empty Environment]")
            return

        # Find bounds
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        grid_entities = []
        
        for entity in entities:
            if isinstance(entity.state.position, Position_2D):
                pos = entity.state.position
                min_x = min(min_x, pos.x)
                max_x = max(max_x, pos.x)
                min_y = min(min_y, pos.y)
                max_y = max(max_y, pos.y)
                grid_entities.append(entity)
        
        if min_x == float('inf'):
             self._render_generic(out_func)
             return

        # Add some padding
        padding = 1
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding

        # Create grid representation
        width = int(max_x - min_x + 1)
        height = int(max_y - min_y + 1)
        
        # Helper to convert world coords to grid index
        def to_grid(x, y):
             return int(y - min_y), int(x - min_x) # row, col

        # Initialize grid with empty lists to hold entities
        grid = [[[] for _ in range(width)] for _ in range(height)]

        for entity in grid_entities:
            r, c = to_grid(entity.state.position.x, entity.state.position.y)
            if 0 <= r < height and 0 <= c < width:
                grid[r][c].append(entity)

        # Render grid
        # Top Border
        out_func("+" + "-" * width + "+")

        # Print from top (max_y) to bottom (min_y)
        for r in range(height - 1, -1, -1):
            line_str = "|" # Left Border
            for c in range(width):
                cell_entities = grid[r][c]
                
                # Get environment color for this position
                # Assuming Position_2D, we recreate the position object or pass coordinates if the env supports it
                # The env get_position_color takes a Position object. 
                # We need to construct a Position_2D object relative to the grid
                # min_x, min_y were offset by padding. 
                # Actual coord = c + min_x, r + min_y
                actual_x = c + min_x
                actual_y = r + min_y
                # We need to import Position_2D but it might be circular or we can use the type from env
                # For now let's assume we can instantiate it if we see it's 2D.
                # But wait, we are in render_2d, so we know it is 2D.
                # However, importing Position_2D here might be cleaner at top level, but let's just cheat and check the type of entity positions
                # Or just duplicate the simple class structure if needed, or better, reuse the one from env if possible.
                # Actually, we imported Position_2D at top of file.
                pos = Position_2D(int(actual_x), int(actual_y))
                env_color = self.env.get_position_color(pos)

                if not cell_entities:
                    sym = "."
                    if env_color:
                        sym = self._colorize(sym, env_color)
                    line_str += sym
                elif len(cell_entities) == 1:
                    e = cell_entities[0]
                    sym = self._get_symbol(e)
                    col = self._get_entity_color(e)
                    line_str += self._colorize(sym, col)
                else:
                    # Handle Stacking
                    # Priority: Agent > Other
                    agents = [e for e in cell_entities if hasattr(e, 'actions_on_self') or getattr(e, 'is_agent', False) or 'Agent' in e.__class__.__name__]
                    
                    if len(agents) > 1:
                        # Multiple agents
                        line_str += self._colorize("+", "MAGENTA")
                    elif len(agents) == 1:
                        # 1 Agent on top of stuff
                        e = agents[0]
                        line_str += self._colorize(self._get_symbol(e), self._get_entity_color(e)) 
                    else:
                        # Multiple non-agents
                        count = len(cell_entities)
                        sym = str(count) if count < 10 else "*"
                        line_str += self._colorize(sym, "CYAN")
            out_func(line_str)

    def _render_generic(self, out_func):
        """
        Fallback renderer for non-spatial or unknown environments.
        """
        out_func("Generic Render:")
        for entity in self.env.state.entities:
            out_func(f"{self._colorize(entity.properties.name, self._get_entity_color(entity))}: {entity.state.position}")

    def _get_symbol(self, entity: Entity) -> str:
        """
        Returns a single character symbol for an entity.
        Prioritizes an explicit 'symbol' property if it exists.
        """
        if hasattr(entity, 'symbol'):
            return str(entity.symbol)[0]
        if hasattr(entity, 'properties') and hasattr(entity.properties, 'symbol'):
             return str(entity.properties.symbol)[0]
        
        # Default logic
        name = entity.properties.name if hasattr(entity.properties, 'name') else "Unamed"
        return name[0].upper()

import re

class VectorAsciiRenderer:
    """
    Renders multiple environments in a grid layout.
    """
    def __init__(self, envs: list[Environment], cols: int = 2):
        self.envs = envs
        self.cols = cols
        # Regex to strip ANSI escape codes
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def _visual_len(self, s: str) -> int:
        return len(self.ansi_escape.sub('', s))

    def render(self, count: Optional[int] = None, clear: bool = True, show_legend: bool = True, return_string: bool = False) -> Optional[str]:
        """
        Renders the vector of environments.
        :param count: Max number of environments to render. If None, renders all.
        :param clear: Whether to clear the console before rendering.
        :param show_legend: Whether to show a consolidated legend at the bottom.
        :param return_string: Whether to return the string instead of printing.
        """
        buffer = []
        def out(s):
            buffer.append(str(s))

        limit = count if count is not None else len(self.envs)
        targets = self.envs[:limit]
        
        if not targets:
            out("No environments to render.")
            if return_string:
                return "\n".join(buffer)
            print("\n".join(buffer))
            return

        # 1. Render all selected envs to strings (WITHOUT LEGEND, With Explicit Index)
        rendered_blocks = []
        for i, env in enumerate(targets):
             # Pass explicit label index
             r_str = env.render(return_string=True, clear=False, show_legend=False, label=str(i))
             if r_str is None:
                 rendered_blocks.append(["[Error Rendering]"])
             else:
                 rendered_blocks.append(r_str.split('\n'))

        # 2. Normalize and Gridify
        rows = []
        for i in range(0, len(rendered_blocks), self.cols):
            chunk = rendered_blocks[i:i + self.cols]
            
            # Find max height in this chunk (row of grid)
            max_h = max(len(block) for block in chunk)
            
            # Pad blocks to match height
            padded_chunk = []
            
            for block in chunk:
                if not block:
                    padded_chunk.append([""] * max_h)
                    continue

                # Calculate max visual width of this block
                max_w = max(self._visual_len(line) for line in block)
                
                new_block = []
                for j in range(max_h):
                    if j < len(block):
                        line = block[j]
                        vis_len = self._visual_len(line)
                        padding = max_w - vis_len
                        
                        # Center align: split padding
                        pad_left = padding // 2
                        pad_right = padding - pad_left
                        
                        new_block.append(" " * pad_left + line + " " * pad_right)
                    else:
                        # Pad vertical height with empty space
                        new_block.append(" " * max_w)
                padded_chunk.append(new_block)
            
            # Stitch lines together horizontally with spacing
            row_lines = []
            for h in range(max_h):
                line_parts = [block[h] for block in padded_chunk]
                # Add outer borders: || Part || Part ||
                row_lines.append(" || " + " || ".join(line_parts) + " || ")
            
            rows.extend(row_lines)
            
            # Add separator between grid rows, matching the column structure
            if i + self.cols < len(rendered_blocks):
                 sep_parts = []
                 for block in padded_chunk:
                     # Use the visual length of the block
                     width = self._visual_len(block[0])
                     sep_parts.append("=" * width)
                 
                 # Add outer separators for horizontal line too
                 rows.append(" || " + " || ".join(sep_parts) + " || ")

        out("\n".join(rows))
        
        # 3. Consolidated Legend
        if show_legend and targets:
            out("\n" + "=" * 50)
            # Aggregate all entities
            all_entities = []
            for env in targets:
                all_entities.extend(env.state.entities)
            
            # Use the renderer of the first env to draw the legend
            first_env = targets[0]
            if not hasattr(first_env, '_renderer'):
                # Force init renderer
                first_env.render(return_string=True, show_legend=False)
            
            # We call _render_legend on the renderer instance, passing output to buffer append
            first_env._renderer._render_legend(out, entities=all_entities)
            
        final_str = "\n".join(buffer)
        if return_string:
            return final_str
        
        if clear:
             os.system('cls' if os.name == 'nt' else 'clear')
        print(final_str)

def render_vector_envs(envs: list[Environment], cols: int = 2, count: Optional[int] = None, clear: bool = True, show_legend: bool = True, return_string: bool = False):
    """
    Helper function to render a list of environments in a grid.
    """
    renderer = VectorAsciiRenderer(envs, cols)
    return renderer.render(count=count, clear=clear, show_legend=show_legend, return_string=return_string)
