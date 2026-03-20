from __future__ import annotations

from tests.run_tests.common import choose_mode
from tests.test_envs.healing_shrine_env import run_healing_shrine_env


def main() -> None:
    print(run_healing_shrine_env(mode=choose_mode()))


if __name__ == "__main__":
    main()
