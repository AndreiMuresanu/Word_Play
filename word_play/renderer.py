import re
import sys
import shutil
from enum import Enum
from typing import List, Protocol, runtime_checkable, Any, Optional
from functools import lru_cache
from dataclasses import dataclass

from word_play.environment import Environment, Entity

# Module-level constant for ANSI escape codes
ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class Color(Enum):
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    
    @classmethod
    def from_str(cls, name: str) -> 'Color':
        """Safely returns a Color from string, defaulting to WHITE."""
        try:
            return cls[name.upper()]
        except (KeyError, AttributeError):
            return cls.WHITE

@runtime_checkable
class Renderable(Protocol):
    """Protocol defining what an entity must provide to be rendered."""
    @property
    def symbol(self) -> str: ...
    
    @property
    def color(self) -> Any: ... # type: ignore - strict type would represent Color or specific str

class AsciiRenderer:
    """
    Renders a Simulation Environment to the terminal using ASCII/Unicode characters.
    
    Coordinate System:
    - The renderer assumes a Cartesian coordinate system where (0,0) is at the BOTTOM-LEFT.
    - Grid rows are printed from Top (Max Y) to Bottom (Y=0).
    """

    def __init__(self, env: Environment):
        """
        Initialize the renderer.
        
        Args:
            env: The environment instance to render.
        """
        self.env = env
        self._last_render_height = 0

    @lru_cache(maxsize=1024)
    def _visual_len(self, s: str) -> int:
        """Returns the visual length of a string, ignoring ANSI codes."""
        return len(ANSI_ESCAPE_PATTERN.sub('', s))

    def _colorize(self, text: str, color_val: Any) -> str:
        """Wraps text in ANSI color codes."""
        if isinstance(color_val, Color):
            color_code = color_val.value
        elif isinstance(color_val, str):
            # Fallback for legacy string colors if not fully refactored
            color_code = Color.from_str(color_val).value
        else:
            return text
            
        return f"{color_code}{text}{Color.RESET.value}"

    def _get_cell_representation(self, x: int, y: int, max_chars: int) -> str:
        """
        Determines the string representation for a specific grid cell.
        Truncates to max_chars based on priority.
        """
        cell_entities = []
        for entity in self.env.state.entities:
            if not isinstance(entity, Entity): continue
            pos = entity.state.position
            if getattr(pos, 'x', -1) == x and getattr(pos, 'y', -1) == y:
                cell_entities.append(entity)
        
        if not cell_entities:
            return " " * max_chars # Blank space padding? Or just empty " " and render handles padding?
            # Render handles padding to ensure alignment. Return empty string or single space?
            # Return empty string, render will pad.
            return ""

        # Priority Sort: High Priority First (rendered first)
        # Agent(30) > Item(20) > Structure(10)
        def priority(e: Entity) -> int:
            props = getattr(e, 'properties', None)
            name = getattr(props, 'name', '').lower()
            if 'agent' in name or 'chef' in name: return 30
            if getattr(props, 'blocking', False): return 10 
            return 20 
            
        # Reverse=True so highest priority is first in the list
        cell_entities.sort(key=priority, reverse=True)
        
        # Build NxN Grid
        symbols = []
        # Total capacity = max_chars * max_chars
        capacity = max_chars * max_chars
        
        count = 0
        for e in cell_entities:
            if count >= capacity: break
            
            # Prefer dynamic symbol property (e.g. for Agents with orientation)
            # then fallback to static property
            sym = getattr(e, 'symbol', None)
            if sym is None:
                props = getattr(e, 'properties', None)
                sym = getattr(props, 'symbol', '?')
                
            props = getattr(e, 'properties', None)
            color = getattr(props, 'color', 'WHITE')
            
            symbols.append(self._colorize(sym, color))
            count += 1
            
        # Pad with spaces to fill capacity? 
        # Actually we construct lines later. We just return the list of N*N symbols (or fewer).
        # Pad the symbols list to capacity with empty strings for consistent slicing later
        symbols.extend([" "] * (capacity - len(symbols)))
        return symbols

    def render(self, *, in_place: bool = False, clear: bool = False, label: str = "", max_cell_width: int = 4) -> None:
        """
        Renders the current state of the environment.
        """
        
        # 1. Bounds
        max_x, max_y = 0, 0
        all_pos = [e.state.position for e in self.env.state.entities if hasattr(e.state.position, 'x')]
        if all_pos:
            max_x = max(int(p.x) for p in all_pos)
            max_y = max(int(p.y) for p in all_pos)
        else:
            max_x, max_y = 5, 5
            
        width = max_x + 1
        height = max_y + 1

        # 2. Fixed Column Widths (N)
        # All columns are exactly max_cell_width
        col_widths = [max_cell_width] * width

        # 3. Render
        output_lines = []
        output_lines.append(f"|| {label} ||")
        output_lines.append(f"Cells are {max_cell_width}x{max_cell_width}. Displaying up to {max_cell_width*max_cell_width} entities.")
        
        def make_separator():
            parts = ["+"]
            for w in col_widths:
                parts.append("-" * w)
                parts.append("+")
            return "".join(parts)

        separator = make_separator()
        
        for y in range(height - 1, -1, -1):
            output_lines.append(separator)
            
            # Fetch content for all cells in this row
            # row_content[x] = list of colored symbols (up to N*N)
            row_content = []
            for x in range(width):
                # We need a new signature for _get: return LIST of strings (symbols)
                # But I updated it to return symbols list in previous Step. 
                # Wait, my previous Replace was modifying _get_cell_representation to return symbols list.
                # I need to make sure the types match. 
                # _get_cell_representation now returns `List[str]`.
                # I should update type hint in a separate or same edit if possible. 
                # Assuming dynamic python, it works.
                syms = self._get_cell_representation(x, y, max_cell_width) 
                row_content.append(syms)
            
            # We must render N lines for this single Grid Row
            for line_idx in range(max_cell_width):
                line_parts = ["|"]
                for x in range(width):
                    # Get symbols for this cell
                    cell_syms = row_content[x]
                    
                    # Determine which slice of symbols goes on this line
                    # Grid:
                    # Line 0: idx 0..N-1
                    # Line 1: idx N..2N-1
                    start = line_idx * max_cell_width
                    end = start + max_cell_width
                    
                    chunk = cell_syms[start:end]
                    
                    # Join chunk into string
                    content_str = "".join(chunk)
                    
                    # Pad
                    # Visual Length check? 
                    # Each symbol is 1 visual char (ANSI colored).
                    # So len(chunk) is the visual length.
                    padding = max_cell_width - len(chunk)
                    
                    line_parts.append(content_str + " " * padding)
                    line_parts.append("|")
                
                output_lines.append("".join(line_parts))
            
        output_lines.append(separator)

        # Legend (Simplified)
        legend_items = set()
        for e in self.env.state.entities:
            props = getattr(e, 'properties', None)
            if props:
                sym = getattr(props, 'symbol', '?')
                # If agent, use dynamic symbol not generic '?'
                if getattr(e, 'symbol', None): sym = e.symbol
                
                name = getattr(props, 'name', 'Unknown')
                legend_items.add(f"[{sym}] {name}")
        
        if legend_items:
            output_lines.append("Legend: " + "   ".join(sorted(legend_items)))

        # Output
        final_output = "\n".join(output_lines)
        num_lines = len(output_lines)
        
        if clear:
            sys.stdout.write("\033[H\033[2J")
        elif in_place and self._last_render_height > 0:
            sys.stdout.write(f"\033[{self._last_render_height}A\033[J")
            
        sys.stdout.write(final_output + "\n")
        sys.stdout.flush()
        self._last_render_height = num_lines + 1 # +1 for the final newline
