from __future__ import annotations

from types import SimpleNamespace

from word_play.presets.renderers.assets import resolve_wall_sprite
from word_play.presets.renderers.wall_geometry import adjacent_wall_variant_name


def _neighbors(*connections: str) -> dict[str, bool]:
    return {
        "left": "left" in connections,
        "right": "right" in connections,
        "up": "up" in connections,
        "down": "down" in connections,
    }


def test_adjacent_wall_variant_name_uses_canonical_cardinal_order() -> None:
    cases = [
        ((), "flat"),
        (("left",), "left"),
        (("right",), "right"),
        (("up",), "up"),
        (("down",), "down"),
        (("left", "right"), "left_right"),
        (("up", "down"), "up_down"),
        (("left", "up"), "left_up"),
        (("left", "down"), "left_down"),
        (("right", "up"), "right_up"),
        (("right", "down"), "right_down"),
        (("left", "right", "up"), "left_right_up"),
        (("left", "right", "down"), "left_right_down"),
        (("left", "up", "down"), "left_up_down"),
        (("right", "up", "down"), "right_up_down"),
        (("left", "right", "up", "down"), "left_right_up_down"),
    ]

    for connections, expected in cases:
        assert adjacent_wall_variant_name(_neighbors(*connections)) == expected


def test_resolve_wall_sprite_prefers_exact_then_center(tmp_path) -> None:
    wall_dir = tmp_path / "bright_mine_wall"
    wall_dir.mkdir()
    (wall_dir / "bright_mine_wall_left_right_down.png").write_bytes(b"")
    (wall_dir / "bright_mine_wall_center.png").write_bytes(b"")
    renderer = SimpleNamespace(_wall_set_cache={})

    exact_match = resolve_wall_sprite(renderer, str(wall_dir), _neighbors("left", "right", "down"))
    fallback_match = resolve_wall_sprite(renderer, str(wall_dir), _neighbors("left", "up"))

    assert exact_match == f"{wall_dir}/bright_mine_wall_left_right_down.png"
    assert fallback_match == f"{wall_dir}/bright_mine_wall_center.png"


def test_resolve_wall_sprite_uses_flat_for_zero_connections(tmp_path) -> None:
    wall_dir = tmp_path / "bright_mine_wall"
    wall_dir.mkdir()
    (wall_dir / "bright_mine_wall_flat.png").write_bytes(b"")
    renderer = SimpleNamespace(_wall_set_cache={})

    resolved = resolve_wall_sprite(renderer, str(wall_dir), _neighbors())

    assert resolved == f"{wall_dir}/bright_mine_wall_flat.png"


def test_resolve_wall_sprite_uses_axis_fallback_for_single_missing_connection(tmp_path) -> None:
    wall_dir = tmp_path / "overcooked_kitchen_wall"
    wall_dir.mkdir()
    (wall_dir / "overcooked_kitchen_wall_up_down.png").write_bytes(b"")
    (wall_dir / "overcooked_kitchen_wall_left_right.png").write_bytes(b"")
    (wall_dir / "overcooked_kitchen_wall_center.png").write_bytes(b"")
    renderer = SimpleNamespace(_wall_set_cache={})

    down_resolved = resolve_wall_sprite(renderer, str(wall_dir), _neighbors("down"))
    left_resolved = resolve_wall_sprite(renderer, str(wall_dir), _neighbors("left"))

    assert down_resolved == f"{wall_dir}/overcooked_kitchen_wall_up_down.png"
    assert left_resolved == f"{wall_dir}/overcooked_kitchen_wall_left_right.png"
