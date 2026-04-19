"""2-agent demo: Prep loads board, Expediter collects from board, cooks, delivers.

Workflow:
- Prep: Get protein → put in board → leave
- Expediter: Get plate → collect from board → load stove → wait → collect → deliver
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from word_play.presets.movement import Move_Down, Move_Left, Move_Right, Move_Up
from word_play.presets.systems import Collect_From_Crafter, Deliver_Item, Dispense_From_Infinite_Source, Do_Nothing, Pick_Up_Item
from word_play.presets.systems.crafter import Load_Crafter

if TYPE_CHECKING:
    from word_play.core import Action


# PREP: Get protein, put in board, leave (DON'T collect - expediter will)
PREP_COOK_SEQUENCE: list[tuple[type["Action"], str | None]] = [
    # Get protein from fridge
    (Dispense_From_Infinite_Source, "Protein Source"),
    (Do_Nothing, None), (Do_Nothing, None),
    (Pick_Up_Item, "protein"),
    (Do_Nothing, None), (Do_Nothing, None),

    # Walk to chopping board: (1,3) -> (2,3) -> (3,3) -> (4,3) -> (4,2) adjacent to (5,2)
    (Move_Right, None), (Move_Right, None), (Move_Right, None),
    (Move_Down, None),
    (Do_Nothing, None), (Do_Nothing, None),

    # Load protein into board (chops automatically since duration=0)
    (Load_Crafter, "Chopping Board"),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Leave - DON'T collect! Expediter will collect from board
    (Move_Down, None),
    (Move_Left, None), (Move_Left, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Wait for expediter to finish
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
]


# EXPEDITER: Get plate, go to board, collect chopped meat, take to stove, cook, deliver
EXPEDITER_SEQUENCE: list[tuple[type["Action"], str | None]] = [
    # Wait for Prep to load board (~15 steps)
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Get plate: (9,3) -> (9,4) adjacent to Plate Stack (9,5)
    (Move_Up, None),
    (Do_Nothing, None), (Do_Nothing, None),
    (Dispense_From_Infinite_Source, "Plate Stack"),
    (Do_Nothing, None), (Do_Nothing, None),
    (Pick_Up_Item, "plate"),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Go to chopping board: (9,4) -> (8,4) -> (7,4) -> (6,4) -> (5,4) -> (5,3) -> (4,3) adjacent to (5,2)?
    # Actually need to be at (4,2) or (6,2) or (5,1) or (5,3)
    # Let's go: (9,4) down to (9,3), left to (8,3), (7,3), (6,3), (5,3) adjacent to (5,2)
    (Move_Down, None),
    (Move_Left, None), (Move_Left, None), (Move_Left, None), (Move_Left, None),
    (Do_Nothing, None), (Do_Nothing, None),

    # Collect chopped protein FROM the board (must be adjacent!)
    (Collect_From_Crafter, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Go to stove with plate + chopped protein: (5,3) -> (6,3) -> (7,3) -> (7,2) adjacent to (8,2)
    (Move_Right, None), (Move_Right, None),
    (Move_Down, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Load stove: first chopped_protein (index 1), then plate (index 0)?
    # Actually: plate in inventory[0], chopped_protein in inventory[1]
    # Load index 1 first (protein), then index 0 (plate)
    # But load_crafter takes from inventory by index

    # Load chopped_protein (recipe needs chopped_protein + plate)
    # With skip_invalid_actions, need to load in order that matches recipe
    # Recipe: ("chopped_tomato", "chopped_protein") - wait that's the OLD recipe
    # Need to check what recipe Stove has now

    # For now: load both items
    (Load_Crafter, "Stove"),
    (Do_Nothing, None), (Do_Nothing, None),
    (Load_Crafter, "Stove"),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Wait for cooking
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Collect cooked dish
    (Collect_From_Crafter, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Go to delivery: (7,2) -> (7,1) -> (8,1)
    (Move_Down, None),
    (Move_Right, None),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),

    # Deliver!
    (Deliver_Item, "Delivery Hatch"),
    (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None), (Do_Nothing, None),
]


CHEF_SEQUENCE = PREP_COOK_SEQUENCE

__all__ = ["PREP_COOK_SEQUENCE", "EXPEDITER_SEQUENCE", "CHEF_SEQUENCE"]
