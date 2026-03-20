from __future__ import annotations

from tests.run_tests.common import choose_mode
from tests.test_envs.arena_combat_env import run_arena_combat_env


def main() -> None:
    print(run_arena_combat_env(mode=choose_mode()))


if __name__ == "__main__":
    main()
