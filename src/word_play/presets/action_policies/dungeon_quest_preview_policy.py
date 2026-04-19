"""Preset action sequences for the Dungeon Quest environment.

These hardcoded action sequences demonstrate the dungeon quest environment without requiring
an API key. They serve as a "preview" mode showing an agent raiding the dungeon.

Usage:
    from word_play.presets.action_policies.dungeon_quest_preview_policy import DUNGEON_RAIDER_SEQUENCE
    from word_play.presets.action_policies.follow_action_sequence import Follow_Action_Sequence

    raider_policy = Follow_Action_Sequence(DUNGEON_RAIDER_SEQUENCE)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from word_play.presets.movement import Move_Down, Move_Left, Move_Right, Move_Up
from word_play.presets.systems import Do_Nothing
from word_play.presets.systems.combat import Attack

if TYPE_CHECKING:
    from word_play.core import Action

# Action targets are referenced by name; the policy resolves them at runtime
# fmt: off

# Raider: Moves through dungeon, fights enemies, defeats the boss
DUNGEON_RAIDER_SEQUENCE: list[tuple[type["Action"], str | None]] = [
    # Initial approach - move toward first enemy cluster
    (Move_Right, None),
    (Move_Right, None),
    (Move_Right, None),
    (Move_Up, None),

    # Attack Goblin Scout (first enemy)
    (Attack, "Goblin Scout"),
    (Attack, "Goblin Scout"),
    (Do_Nothing, None),  # Wait turn for enemy counters

    # Move toward Bone Guard A
    (Move_Right, None),
    (Move_Down, None),
    (Move_Right, None),

    # Attack Bone Guard A
    (Attack, "Bone Guard"),
    (Attack, "Bone Guard"),
    (Attack, "Bone Guard"),
    (Do_Nothing, None),  # Wait turn

    # Move toward Bone Guard B
    (Move_Right, None),
    (Move_Up, None),
    (Move_Right, None),

    # Attack Bone Guard B
    (Attack, "Bone Guard"),
    (Attack, "Bone Guard"),
    (Attack, "Bone Guard"),
    (Do_Nothing, None),  # Wait turn

    # Move toward Goblin Warrior
    (Move_Right, None),
    (Move_Down, None),

    # Attack Goblin Warrior
    (Attack, "Goblin Warrior"),
    (Attack, "Goblin Warrior"),
    (Attack, "Goblin Warrior"),
    (Attack, "Goblin Warrior"),
    (Do_Nothing, None),  # Wait turn

    # All minions defeated! Move toward boss arena
    (Move_Right, None),
    (Move_Right, None),
    (Move_Up, None),
    (Move_Right, None),

    # Facing the Ash Warden (BOSS)
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack
    (Attack, "Ash Warden"),
    (Do_Nothing, None),  # Boss counterattack

    # Victory! Ash Warden defeated
    # Walk around showing victory lap
    (Move_Left, None),
    (Move_Left, None),
    (Move_Down, None),
    (Move_Down, None),
    (Move_Right, None),
    (Move_Right, None),
    (Move_Up, None),
    (Move_Up, None),

    # Idle for remaining episode duration
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
]

# Alternative: A more defensive sequence that waits and observes
DUNGEON_RAIDER_DEFENSIVE_SEQUENCE: list[tuple[type["Action"], str | None]] = [
    # Observe from starting position
    (Do_Nothing, None),
    (Do_Nothing, None),

    # Move cautiously toward first threat
    (Move_Right, None),
    (Do_Nothing, None),
    (Move_Up, None),
    (Do_Nothing, None),

    # Deal with nearby enemy
    (Attack, "Goblin Scout"),
    (Do_Nothing, None),
    (Attack, "Goblin Scout"),

    # Retreat to heal/stabilize
    (Move_Left, None),
    (Do_Nothing, None),
    (Do_Nothing, None),

    # Push forward again
    (Move_Right, None),
    (Move_Right, None),
    (Attack, "Bone Guard"),
    (Do_Nothing, None),

    # Continue through dungeon...
    (Move_Right, None),
    (Move_Up, None),
    (Attack, "Bone Guard"),
    (Do_Nothing, None),

    # Extra idle padding
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
    (Do_Nothing, None),
]

# fmt: on

__all__ = ["DUNGEON_RAIDER_SEQUENCE", "DUNGEON_RAIDER_DEFENSIVE_SEQUENCE"]
