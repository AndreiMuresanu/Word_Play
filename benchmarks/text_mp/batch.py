"""Run N episodes of a text_mp substrate and report mean±std per-capita return.

Turns single noisy episodes into stable estimates for the LLM-vs-random gap.

Examples:
    # random baseline, 10 episodes
    python benchmarks/text_mp/batch.py commons_harvest open --policy random -n 10 --agent-count 2

    # compare random vs llm in one shot
    python benchmarks/text_mp/batch.py commons_harvest open --compare -n 5 --agent-count 2
"""
from __future__ import annotations

import argparse
import importlib
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
for p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from benchmarks.text_mp.core.runner import run_episode  # noqa: E402
from benchmarks.text_mp.core.timing import BENCHMARK_STEPS  # noqa: E402


def _silent(*_args, **_kwargs) -> None:
    pass


def load_substrate(name: str):
    builder = importlib.import_module(f"benchmarks.text_mp.substrates.{name}.builder")
    variants = importlib.import_module(f"benchmarks.text_mp.substrates.{name}.variants")
    return builder.build_env, variants.VARIANTS


def run_batch(
    *,
    substrate: str,
    variant_name: str,
    policy: str,
    n_episodes: int,
    agent_count: int | None,
    model_name: str,
    max_steps: int,
) -> list[float]:
    build_env, variants = load_substrate(substrate)
    variant = variants[variant_name]
    per_capita: list[float] = []
    for ep in range(n_episodes):
        env = build_env(
            variant=variant,
            agent_count=agent_count,
            policy_kind=policy,
            model_name=model_name,
        )
        result = run_episode(env, max_steps=max_steps, print_actions=False, print_fn=_silent)
        per_capita.append(result.per_capita_return)
        print(f"  [{policy}] ep {ep + 1}/{n_episodes}: per-capita {result.per_capita_return:.2f}", flush=True)
    return per_capita


def summarize(label: str, values: list[float]) -> dict:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    stats = {"label": label, "n": len(values), "mean": mean, "std": std,
             "min": min(values), "max": max(values)}
    print(f"{label:>8}: mean {mean:7.2f}  std {std:6.2f}  "
          f"min {min(values):7.2f}  max {max(values):7.2f}  (n={len(values)})")
    return stats


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("substrate")
    p.add_argument("variant")
    p.add_argument("--policy", choices=["random", "llm"], default="random")
    p.add_argument("--compare", action="store_true", help="run both random and llm and report the gap")
    p.add_argument("-n", "--n-episodes", type=int, default=10)
    p.add_argument("--agent-count", type=int, default=None)
    p.add_argument("--model-name", default="openai/gpt-4o-mini")
    p.add_argument("--max-steps", type=int, default=BENCHMARK_STEPS)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    common = dict(substrate=args.substrate, variant_name=args.variant,
                  agent_count=args.agent_count, model_name=args.model_name,
                  max_steps=args.max_steps, n_episodes=args.n_episodes)

    print(f"=== {args.substrate}:{args.variant} | {args.n_episodes} episodes | "
          f"agents={args.agent_count or 'default'} ===")

    policies = ["random", "llm"] if args.compare else [args.policy]
    results = {}
    for policy in policies:
        vals = run_batch(policy=policy, **common)
        results[policy] = summarize(policy, vals)

    if args.compare:
        gap = results["llm"]["mean"] - results["random"]["mean"]
        ratio = results["llm"]["mean"] / results["random"]["mean"] if results["random"]["mean"] else float("inf")
        print(f"\nGAP (llm - random): {gap:+.2f}   ratio: {ratio:.2f}x")


if __name__ == "__main__":
    main()
