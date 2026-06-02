from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from word_play.core import Action_Selection, Environment, Observation

from .draw import render_environment
from .runtime import handle_entity_click, init_pygame_if_needed


def renderer_for_env(env: Environment) -> Any | None:
    return getattr(env, "renderer_impl", None)


def renderer_for_observation(observation: Observation) -> Any | None:
    possible_actions = list(getattr(observation, "possible_actions", []))
    if not possible_actions:
        return None
    return renderer_for_env(possible_actions[0].env)


def _set_sidebar(
    env: Environment,
    *,
    header: str,
    lines: list[str],
    selected_action: list[str] | None = None,
    actions: list[str] | None = None,
    compact_observation: bool = False,
) -> None:
    env.hud_sidebar_header = header
    env.hud_sidebar_lines = lines
    env.hud_sidebar_selected_action = selected_action or []
    env.hud_sidebar_actions = actions or []
    env.hud_sidebar_compact_observation = compact_observation
    env.hud_sidebar_width = max(560, int(getattr(env, "hud_sidebar_width", 0) or 0))


def _cancel_human_input() -> None:
    pygame.quit()
    raise KeyboardInterrupt("Human input cancelled.")


def _digit_index(key: int) -> int | None:
    if pygame.K_0 <= key <= pygame.K_9:
        return key - pygame.K_0
    if pygame.K_KP0 <= key <= pygame.K_KP9:
        return key - pygame.K_KP0
    return None


def _observation_lines(observation: Observation) -> list[str]:
    lines = []
    for line in str(observation).strip().splitlines():
        if line.startswith("AVAILABLE ACTIONS (reply with the index):"):
            break
        lines.append(line)
    if not lines:
        return ["Observation:", "(empty)"]
    return ["Observation:", *lines]


def _action_lines(possible_actions: list[Action_Selection], selected_index: int) -> list[str]:
    lines = ["Up/Down select. Enter choose.", "", "Possible Actions:"]
    for index, action_selection in enumerate(possible_actions):
        prefix = ">" if index == selected_index else " "
        lines.append(f"{prefix} [{index}] {action_selection}")
    return lines


def prompt_human_action(
    renderer: Any,
    observation: Observation,
    *,
    max_attempts: int = 10,
) -> Action_Selection:
    possible_actions = list(observation.possible_actions)
    if not possible_actions:
        raise RuntimeError("No possible actions to select.")

    env = possible_actions[0].env
    agent = getattr(observation, "agent", possible_actions[0].actor)
    selected_index = 0
    clock = pygame.time.Clock()

    while True:
        _set_sidebar(
            env,
            header=f"{agent.name} Action",
            lines=[
                *_observation_lines(observation),
            ],
            selected_action=["Selected Action:", f"[{selected_index}] {possible_actions[selected_index]}"],
            actions=_action_lines(possible_actions, selected_index),
            compact_observation=True,
        )
        init_pygame_if_needed(renderer)
        render_environment(renderer, env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _cancel_human_input()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                handle_entity_click(renderer, env, event.pos, button=event.button)
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_ESCAPE:
                _cancel_human_input()
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return possible_actions[selected_index]
            if event.key in (pygame.K_DOWN, pygame.K_j):
                selected_index = (selected_index + 1) % len(possible_actions)
                continue
            if event.key in (pygame.K_UP, pygame.K_k):
                selected_index = (selected_index - 1) % len(possible_actions)
                continue

            digit_index = _digit_index(event.key)
            if digit_index is not None and digit_index < len(possible_actions):
                selected_index = digit_index

        clock.tick(30)


def _kwarg_lines(action_selection: Action_Selection, text: str, error_message: str | None) -> list[str]:
    lines = [
        str(action_selection),
        "Required Arguments:",
    ]
    for name, arg in action_selection.required_kwargs.items():
        desc = arg.arg_description(action_selection.actor, action_selection.target_entity, action_selection.env)
        lines.append(f"{name}: {desc}")
    lines.extend([
        "",
        "Enter values separated by ';'",
        f"> {text}",
    ])
    if error_message:
        lines.extend(["", f"Error: {error_message}"])
    return lines


def prompt_human_action_kwargs(
    renderer: Any,
    action_selection: Action_Selection,
    *,
    max_attempts: int = 10,
) -> dict:
    env = action_selection.env
    text = ""
    error_message = None
    attempts = 0
    clock = pygame.time.Clock()

    while attempts < max_attempts:
        _set_sidebar(
            env,
            header="Action Arguments",
            lines=_kwarg_lines(action_selection, text, error_message),
            selected_action=["Chosen Action:", str(action_selection)],
        )
        init_pygame_if_needed(renderer)
        render_environment(renderer, env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _cancel_human_input()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                handle_entity_click(renderer, env, event.pos, button=event.button)
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_ESCAPE:
                _cancel_human_input()
            if event.key == pygame.K_BACKSPACE:
                text = text[:-1]
                continue
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                try:
                    return action_selection.parse_and_validate_kwarg_list(text)
                except Exception as exc:
                    attempts += 1
                    error_message = str(exc)
                    continue
            if event.unicode and event.unicode.isprintable():
                text += event.unicode

        clock.tick(30)

    raise RuntimeError("Too many invalid attempts entering arguments.")


def prompt_human_text(
    renderer: Any,
    env: Environment,
    *,
    header: str,
    lines: list[str],
) -> str:
    text = ""
    clock = pygame.time.Clock()

    while True:
        _set_sidebar(
            env,
            header=header,
            lines=[
                *lines,
                "",
                "Type your message. Enter sends.",
                f"> {text}",
            ],
        )
        init_pygame_if_needed(renderer)
        render_environment(renderer, env)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _cancel_human_input()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                handle_entity_click(renderer, env, event.pos, button=event.button)
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_ESCAPE:
                _cancel_human_input()
            if event.key == pygame.K_BACKSPACE:
                text = text[:-1]
                continue
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return text
            if event.unicode and event.unicode.isprintable():
                text += event.unicode

        clock.tick(30)
