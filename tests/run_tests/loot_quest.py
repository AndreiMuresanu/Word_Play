from __future__ import annotations

from tests.run_tests.common import choose_mode
from tests.test_envs.loot_quest_env import run_loot_quest_env


def main() -> None:
    print(run_loot_quest_env(mode=choose_mode()))


if __name__ == "__main__":
    main()
