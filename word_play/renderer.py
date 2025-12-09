import os
import re
import math
from typing import Optional, Union, List, Tuple
from word_play.environment import Environment, Entity, Position
from word_play.presets.movement_system_presets import Position_2D, Position_1D

class AsciiRenderer:
    """
    A dynamic ASCII renderer that supports both single and multiple environment (vector) rendering.
    Uses a grid-based layout with customized borders and separators.
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

    def __init__(self, envs: Union[Environment, List[Environment]], cols: int = 2, tile_size: Union[int, str] = 1):
        if isinstance(envs, Environment):
            self.envs = [envs]
        else:
            self.envs = envs
            
        self.cols = cols
        self.tile_size = tile_size
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def _colorize(self, text: str, color: str) -> str:
        code = self.COLORS.get(color.upper(), self.COLORS['RESET'])
        return f"{code}{text}{self.COLORS['RESET']}"

    def _visual_len(self, s: str) -> int:
        return len(self.ansi_escape.sub('', s))

    def _get_entity_color(self, entity: Entity) -> str:
        if hasattr(entity, 'color'):
             return entity.color
        if hasattr(entity, 'properties') and hasattr(entity.properties, 'color'):
             return entity.properties.color
        
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

    def _get_symbol(self, entity: Entity) -> str:
        if hasattr(entity, 'symbol'):
            return str(entity.symbol)[0]
        if hasattr(entity, 'properties') and hasattr(entity.properties, 'symbol'):
             return str(entity.properties.symbol)[0]
        
        name = entity.properties.name if hasattr(entity.properties, 'name') else "Unamed"
        return name[0].upper()

    def _render_single_env_frame(self, env: Environment, label_override: Optional[str] = None) -> List[str]:
        """
        Generates the string block (header + grid + extras) for a single environment.
        Does NOT include the legend.
        """
        buffer = []
        def out(s):
            buffer.append(str(s))

        # Header
        if label_override:
             header_text = f"Environment {label_override}"
        else:
             header_text = f"Environment: {env.properties.description}"
        out(header_text)

        # Body
        if isinstance(env.movement_system.position_type, type(Position_2D)) or env.movement_system.position_type == Position_2D:
            self._render_2d_grid(env, out)
        else:
            self._render_generic(env, out)

        # Rewards (Optional)
        if hasattr(env, 'last_rewards') and env.last_rewards:
            rewards = [r for r in env.last_rewards if r is not None]
            if rewards:
                 out(f"Last Rewards: {rewards}")

        return buffer

    def _render_2d_grid(self, env: Environment, out_func):
        entities = env.state.entities
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
             self._render_generic(env, out_func)
             return

        padding = 1
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding

        width = int(max_x - min_x + 1)
        height = int(max_y - min_y + 1)
        
        def to_grid(x, y):
             return int(y - min_y), int(x - min_x)

        grid = [[[] for _ in range(width)] for _ in range(height)]

        for entity in grid_entities:
            r, c = to_grid(entity.state.position.x, entity.state.position.y)
            if 0 <= r < height and 0 <= c < width:
                grid[r][c].append(entity)
        
        # Scale frame width
        # If tile_size was auto-determined, use it, otherwise use instance default
        current_tile_size = getattr(self, '_current_tile_size', 1) 
        if self.tile_size != 'auto': 
            current_tile_size = self.tile_size

        total_width = width * current_tile_size
        
        # Top Border
        out_func("┌" + "─" * total_width + "┐")
        
        for r in range(height - 1, -1, -1):
            # Render each sub-row of the tile
            for sub_r in range(current_tile_size):
                line_str = "│"
                for c in range(width):
                    cell_entities = grid[r][c]
                    
                    # Determine start/end indices for entities in this logical cell
                    start_slot = sub_r * current_tile_size
                    
                    actual_x = c + min_x
                    actual_y = r + min_y
                    pos = Position_2D(int(actual_x), int(actual_y))
                    env_color = env.get_position_color(pos)

                    for sub_c in range(current_tile_size):
                        slot_idx = start_slot + sub_c
                        
                        sym = "."
                        if env_color:
                            sym = self._colorize(sym, env_color)
                        
                        if slot_idx < len(cell_entities):
                            e = cell_entities[slot_idx]
                            max_slots = current_tile_size * current_tile_size
                            
                            # Overflow handling
                            if slot_idx == max_slots - 1 and len(cell_entities) > max_slots:
                                # Calculate how many entities are hidden including this slot
                                # hidden_count = len(cell_entities) - (max_slots - 1)
                                # Show the count as a hex digit (1-9, A-Z) if possible, or '*'
                                # Actually user hates '+'. Let's show count.
                                hidden = len(cell_entities) - slot_idx
                                # If hidden is 1, it means we are replacing the last slot entity with '1'? No that's confusing.
                                # The + usually means "and more".
                                # If we strictly conform to "No +", let's use '*' or just numeric count of TOTAL in cell
                                # But we want to see individual IDs.
                                # Let's show the count of *extra* agents.
                                
                                overflow_str = str(hidden) if hidden < 10 else "*"
                                sym = self._colorize(overflow_str, "MAGENTA")
                            else:
                                raw_sym = self._get_symbol(e)
                                col = self._get_entity_color(e)
                                sym = self._colorize(raw_sym, col)
                        
                        line_str += sym

                out_func(line_str + "│")
        # Bottom Border
        out_func("└" + "─" * total_width + "┘")

    def _render_generic(self, env: Environment, out_func):
        out_func("Generic Render:")
        for entity in env.state.entities:
            out_func(f"{self._colorize(entity.properties.name, self._get_entity_color(entity))}: {entity.state.position}")

    def _render_legend(self, out_func, entities_list):
        unique_entities = {} 
        for entity in entities_list:
            sym = self._get_symbol(entity)
            col = self._get_entity_color(entity)
            name = getattr(entity.properties, 'name', 'Unknown')
            key = (sym, col)
            if key not in unique_entities:
                unique_entities[key] = name
        
        if ('+', 'MAGENTA') in unique_entities:
             del unique_entities[('+', 'MAGENTA')]
        
        out_func("Legend:")
        legend_items = []
        for (sym, col), name in unique_entities.items():
            colored_sym = self._colorize(sym, col)
            legend_items.append(f"[{colored_sym}] {name}")
        
        chunk_size = 3
        for i in range(0, len(legend_items), chunk_size):
            out_func("   ".join(legend_items[i:i+chunk_size]))
        out_func("")

    def render(self, count: Optional[int] = None, clear: bool = True, show_legend: bool = True, return_string: bool = False, envs: list = None, number_of_environments: Optional[int] = None, label: Optional[str] = None) -> Optional[str]:
        """
        Main render method.
        If 'envs' is passed, it overrides self.envs (useful for backward compat / flexibility).
        If 'label' is passed, it overrides the header label (only used if rendering a single env this way).
        """
        # Determine targets
        targets = envs if envs else self.envs
        
        # Handle 'number_of_environments' alias for 'count'
        limit = count if count is not None else number_of_environments
        if limit is not None:
             targets = targets[:limit]

        # Auto-scaling logic if enabled
        if self.tile_size == 'auto':
            max_density = 1
            for env in targets:
                # Poor man's density check: iterate all entities and count per pos
                # Optimization: do this only if 'auto'
                counts = {}
                for e in env.state.entities:
                    p = (e.state.position.x, e.state.position.y) if hasattr(e.state.position, 'x') else str(e.state.position)
                    counts[p] = counts.get(p, 0) + 1
                if counts:
                    max_density = max(max_density, max(counts.values()))
            
            # Calculate required tile size (width/height of square)
            # ceil(sqrt(max_density))
            req_size = math.ceil(math.sqrt(max_density))
            self._current_tile_size = max(1, req_size)
        else:
            self._current_tile_size = self.tile_size

        buffer = []
        def out(s):
             buffer.append(str(s))

        if not targets:
            out("No environments to render.")
            final_str = "\n".join(buffer)
            if return_string: return final_str
            print(final_str)
            return

        # 1. Generate Blocks
        rendered_blocks = []
        for i, env in enumerate(targets):
            # If multiple targets, we use index as label, unless specific label provided for single
            lbl = str(i)
            if len(targets) == 1 and label:
                lbl = label
            # If only 1 env and no label provided, we pass None to let it use env description
            if len(targets) == 1 and not label:
                lbl = None
            
            block = self._render_single_env_frame(env, label_override=lbl)
            rendered_blocks.append(block)

        # 2. Gridify
        rows = []
        for i in range(0, len(rendered_blocks), self.cols):
            chunk = rendered_blocks[i:i + self.cols]
            max_h = max(len(block) for block in chunk)
            
            padded_chunk = []
            for block in chunk:
                if not block:
                    padded_chunk.append([""] * max_h)
                    continue
                
                max_w = max(self._visual_len(line) for line in block)
                new_block = []
                for j in range(max_h):
                    if j < len(block):
                        line = block[j]
                        vis_len = self._visual_len(line)
                        padding = max_w - vis_len
                        pad_left = padding // 2
                        pad_right = padding - pad_left
                        new_block.append(" " * pad_left + line + " " * pad_right)
                    else:
                        new_block.append(" " * max_w)
                padded_chunk.append(new_block)
            
            # Stitch with vertical borders
            row_lines = []
            for h in range(max_h):
                line_parts = [block[h] for block in padded_chunk]
                row_lines.append(" || " + " || ".join(line_parts) + " || ")
            
            rows.extend(row_lines)
            
            # Horizontal Separator
            if i + self.cols < len(rendered_blocks):
                 sep_parts = []
                 for block in padded_chunk:
                     width = self._visual_len(block[0])
                     sep_parts.append("=" * width)
                 rows.append(" || " + " || ".join(sep_parts) + " || ")

        out("\n".join(rows))

        # 3. Legend
        if show_legend:
            out("\n" + "=" * 50)
            all_entities = []
            for env in targets:
                all_entities.extend(env.state.entities)
            self._render_legend(out, all_entities)

        final_str = "\n".join(buffer)

        if return_string:
            return final_str
        
        if clear:
             os.system('cls' if os.name == 'nt' else 'clear')
        print(final_str)

# Backward compatibility / Helper
def render_vector_envs(envs: list[Environment], cols: int = 2, count: Optional[int] = None, clear: bool = True, show_legend: bool = True, return_string: bool = False, tile_size: Union[int, str] = 1):
    renderer = AsciiRenderer(envs, cols, tile_size=tile_size)
    return renderer.render(count=count, clear=clear, show_legend=show_legend, return_string=return_string)
