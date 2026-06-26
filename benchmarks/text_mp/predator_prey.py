from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from benchmarks.text_mp.core.runner import run_episode  # noqa: E402
from benchmarks.text_mp.core.timing import BENCHMARK_STEPS  # noqa: E402
from benchmarks.text_mp.substrates.predator_prey.builder import build_env  # noqa: E402
from benchmarks.text_mp.substrates.predator_prey.variants import VARIANTS  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Predator Prey Text Melting Pot benchmark.")
    parser.add_argument("variant", choices=sorted(VARIANTS))
    parser.add_argument("--agent-count", type=int, default=None)
    parser.add_argument("--policy", choices=["random", "llm", "human"], default="random")
    parser.add_argument("--model-name", default="openai/gpt-4o-mini")
    parser.add_argument("--max-steps", type=int, default=BENCHMARK_STEPS)
    parser.add_argument("--print-raw", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    variant = VARIANTS[args.variant]
    env = build_env(
        variant=variant,
        agent_count=args.agent_count,
        policy_kind=args.policy,
        model_name=args.model_name,
    )

    print(f"Text Melting Pot: predator_prey:{variant.name}")
    print(f"Policy: {args.policy}")
    run_episode(
        env,
        max_steps=args.max_steps,
        event_attributes=("predator_prey_events",),
        print_raw_responses=args.print_raw,
    )


if __name__ == "__main__":
    main()
