from __future__ import annotations


def choose_mode() -> str:
    prompt = "Choose mode: [1] predefined, [2] random > "
    for _ in range(10):
        choice = input(prompt).strip().lower()
        if choice in {"1", "predefined", "p"}:
            return "predefined"
        if choice in {"2", "random", "r"}:
            return "random"
        print("Please enter 1/predefined or 2/random.")
    raise RuntimeError("Too many invalid attempts choosing a mode.")
