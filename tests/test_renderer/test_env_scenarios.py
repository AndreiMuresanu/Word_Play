from __future__ import annotations

import pytest

from tests.test_envs.arena_combat_env import run_arena_combat_env
from tests.test_envs.dungeon_walk_env import run_dungeon_walk_env
from tests.test_envs.healing_shrine_env import run_healing_shrine_env
from tests.test_envs.loot_quest_env import run_loot_quest_env


@pytest.mark.scenario
def test_arena_combat_predefined(test_verbosity: int) -> None:
    result = run_arena_combat_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "remaining_entities": ["Agent A", "Agent C"],
        "agent_c_health": 2,
    }


@pytest.mark.scenario
def test_healing_shrine_predefined(test_verbosity: int) -> None:
    result = run_healing_shrine_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "fighter_health": 3,
    }


@pytest.mark.scenario
def test_loot_quest_predefined(test_verbosity: int) -> None:
    result = run_loot_quest_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "rogue_position": 2,
        "rogue_inventory": ["Potion Drop"],
        "remaining_entities": ["Rogue", "Potion Drop"],
    }


@pytest.mark.scenario
def test_dungeon_walk_predefined(test_verbosity: int) -> None:
    result = run_dungeon_walk_env(mode="predefined", verbosity=test_verbosity)
    assert result == {
        "random_order": {
            "description": "Small dungeon walk smoke environment.",
            "entities": [
                {"name": "Buddy", "position": "(1, 2)", "tags": ["agent"]},
                {"name": "Scout", "position": "(1, 1)", "tags": ["agent"]},
                {"name": "Wall", "position": "(1, 0)", "tags": ["wall"]},
            ],
            "agent_names": ["Scout", "Buddy"],
        },
        "randomize_agent_order": {
            "description": "Small dungeon walk smoke environment.",
            "entities": [
                {"name": "Buddy", "position": "(1, 2)", "tags": ["agent"]},
                {"name": "Scout", "position": "(1, 1)", "tags": ["agent"]},
                {"name": "Wall", "position": "(1, 0)", "tags": ["wall"]},
            ],
            "agent_names": ["Scout", "Buddy"],
        },
    }
