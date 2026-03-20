from __future__ import annotations

from tests.run_tests.common import choose_mode
from tests.test_envs.dungeon_walk_env import run_dungeon_walk_env


def main() -> None:
    print(run_dungeon_walk_env(mode=choose_mode()))


if __name__ == "__main__":
    main()
