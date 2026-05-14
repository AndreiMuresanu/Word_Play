from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Word Play pytest suite.")
    parser.add_argument(
        "--test-verbosity",
        type=int,
        default=0,
        help="Scenario trace verbosity: 0 keeps tests quiet, 1+ prints more trace output.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Additional arguments passed through to pytest.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args, pytest_args = parser.parse_known_args()

    root = Path(__file__).resolve().parents[2]

    if importlib.util.find_spec("pytest") is None:
        print(
            "pytest is not installed in the active interpreter. "
            "Install the project with test dependencies first, for example: "
            f"{sys.executable} -m pip install -e .[test]",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        f"--test-verbosity={args.test_verbosity}",
        *pytest_args,
        *args.pytest_args,
    ]
    return subprocess.run(command, cwd=root).returncode


if __name__ == "__main__":
    raise SystemExit(main())
