"""Semantic themes: map sprite-names ("tree", "grass", "villager") to files.

A theme binds an environment to ONE cohesive sprite pack — a thin, pack-specific
name→file lookup. Authors write ``Renderable(sprite_path="tree")`` and never
touch filenames; swapping the theme re-skins the whole world. A literal path in
``sprite_path`` bypasses the theme. (How a thing *behaves* — light, smoke, floor
— is a theme-independent ``behaviour``; see ``behaviours.py``.)

    renderer = Pygame_Renderer(Grid_Layout_Adapter(), theme="interactive_city")
    ...
    Renderable(sprite_path="tree")              # theme resolves the file
    Renderable(sprite_path="explicit/path.png") # literal, bypasses the theme

Themes are data: every pack ships a ``theme.json`` next to its PNGs, and
``resolve_theme("<pack folder name>")`` loads it. Names are resolved at draw
time; the Renderable is never rewritten.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Directories scanned for drop-in packs (a pack = a folder of PNGs + theme.json).
PACK_SEARCH_ROOTS = (
    "sprite_library/src/generated/worlds",
    "sprite_library/src/generated/benchmarks",
)

MANIFEST_NAME = "theme.json"

@dataclass(slots=True)
class Theme:
    name: str
    root: str                                   # pack directory (repo-relative)
    roles: dict[str, str]                       # role -> filename within root
    wall_roles: dict[str, str] = field(default_factory=dict)  # role -> wall-set subdir
    # roles that emit light by default under dusk/night ambience:
    # role -> (rgb color, radius in tiles, strength). Authors passing an explicit
    # glow keep full control; role defaults fill in only when glow is unset.
    role_glow: dict[str, tuple[tuple[int, int, int], float, float]] = field(default_factory=dict)
    # roles that send up a drift of chimney smoke (drawn automatically)
    role_smoke: frozenset = frozenset()
    # ground roles that fringe over lower-ranked neighbors (soft tile transitions);
    # higher rank paints its edge onto the adjacent lower-ranked tile.
    ground_precedence: dict[str, int] = field(default_factory=dict)
    # UI chrome style for panels/text drawn around the world ("rustic", "slate",
    # "minimal"); None = the renderer's default.
    chrome: str | None = None

    def sprite(self, role: str) -> str | None:
        filename = self.roles.get(role)
        if filename is None:
            return None
        # values inherited from an extended base theme are already qualified
        return filename if "/" in filename else f"{self.root}/{filename}"

    def wall_set(self, role: str) -> str | None:
        subdir = self.wall_roles.get(role)
        if subdir is None:
            return None
        return subdir if "/" in subdir else f"{self.root}/{subdir}"


def theme_from_manifest(manifest_path: Path, *, name: str | None = None) -> Theme:
    """Build a Theme from a pack's theme.json (the pack travels with its data).

    Supports ``"extends": "<other theme>"`` so partial packs (a seasonal reskin,
    a biome variant) only declare the roles they change.
    """
    data = json.loads(manifest_path.read_text())
    pack_dir = manifest_path.parent
    root = data.get("root") or _repo_relative(pack_dir)

    base: Theme | None = None
    extends = data.get("extends")
    if extends:
        base = resolve_theme(extends)

    # inherit fully-qualified paths (rooted in the BASE pack) so non-overridden
    # roles keep resolving even though this theme's root is the child pack dir
    roles = {role: base.sprite(role) for role in base.roles} if base else {}
    roles.update(data.get("roles", {}))
    wall_roles = {role: base.wall_set(role) for role in base.wall_roles} if base else {}
    wall_roles.update(data.get("wall_roles", {}))
    role_glow = dict(base.role_glow) if base else {}
    for role, spec in data.get("role_glow", {}).items():
        color, radius, strength = spec
        role_glow[role] = (tuple(int(c) for c in color), float(radius), float(strength))
    role_smoke = set(base.role_smoke) if base else set()
    role_smoke.update(data.get("role_smoke", []))
    ground_precedence = dict(base.ground_precedence) if base else {}
    ground_precedence.update(data.get("ground_precedence", {}))
    chrome = data.get("chrome") or (base.chrome if base else None)

    return Theme(
        name=name or data.get("name") or pack_dir.name,
        root=root,
        roles=roles,
        wall_roles=wall_roles,
        role_glow=role_glow,
        role_smoke=frozenset(role_smoke),
        ground_precedence=ground_precedence,
        chrome=chrome,
    )


def _project_root() -> Path:
    # themes.py lives at src/word_play/presets/renderers/ -> repo root is 4 up
    return Path(__file__).resolve().parents[4]


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(_project_root()).as_posix()
    except ValueError:
        return str(path)


def _find_pack_manifest(name: str) -> Path | None:
    """Locate theme.json for a named (or path-specified) drop-in pack."""
    candidates: list[Path] = []
    as_path = Path(name)
    candidates.append(as_path / MANIFEST_NAME)
    if as_path.suffix == ".json":
        candidates.append(as_path)
    for search_root in PACK_SEARCH_ROOTS:
        candidates.append(Path(search_root) / name / MANIFEST_NAME)
        candidates.append(_project_root() / search_root / name / MANIFEST_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


THEMES: dict[str, Theme] = {}   # loaded packs, by name (filled lazily)


def resolve_theme(theme: "str | Theme | None") -> Theme | None:
    """Resolve a theme by instance or pack name.

    Any folder with a ``theme.json`` under :data:`PACK_SEARCH_ROOTS` (or a path
    to one) is loadable by name: ``Pygame_Renderer(..., theme="rustic_town")``.
    """
    if theme is None or isinstance(theme, Theme):
        return theme
    if theme in THEMES:
        return THEMES[theme]
    manifest = _find_pack_manifest(theme)
    if manifest is not None:
        if theme in _resolving_themes:
            raise ValueError(
                f"theme 'extends' cycle detected: {' -> '.join([*_resolving_themes, theme])}"
            )
        _resolving_themes.append(theme)
        try:
            loaded = theme_from_manifest(manifest)
        finally:
            _resolving_themes.pop()
        THEMES[theme] = loaded
        return loaded
    raise KeyError(
        f"Unknown theme {theme!r}. Available: {available_themes()} "
        f"(or any pack folder with a {MANIFEST_NAME} under {PACK_SEARCH_ROOTS})"
    )


def available_themes() -> list[str]:
    """Names of every discoverable pack (folders with a theme.json)."""
    names = set(THEMES)
    for search_root in PACK_SEARCH_ROOTS:
        root = _project_root() / search_root
        if root.is_dir():
            names.update(p.parent.name for p in root.glob(f"*/{MANIFEST_NAME}"))
    return sorted(names)


MISSING_ROLE_PREFIX = "__missing_role__/"
NEUTRAL_FLOOR_SPRITE = "__neutral__/floor"   # procedural ground for themeless envs
_warned_missing: set[str] = set()
_resolving_themes: list[str] = []
_lookup_cache: dict[tuple[str | None, str], str | None] = {}


def is_sprite_name(name: str) -> bool:
    """True for a bare sprite-name ("tree"), False for a literal/special path."""
    return "/" not in name and not name.endswith(".png")


def lookup_sprite(theme: Theme | None, name: str) -> str | None:
    """Map a sprite-name to a file path: theme first, then the library index.

    Literal paths pass through unchanged; an unknown name returns ``None``.
    A theme wall role ("wall") resolves to its wall-set's centre tile.
    """
    if not is_sprite_name(name):
        return name
    key = (None if theme is None else theme.name, name)
    if key not in _lookup_cache:
        resolved = None
        if theme is not None:
            resolved = theme.sprite(name)
            if resolved is None and name in theme.wall_roles:
                wall_set = theme.wall_set(name)
                resolved = f"{wall_set}/{wall_set.rsplit('/', 1)[-1]}_center.png"
        if resolved is None:
            from .sprite_index import sprite_path_for_name

            resolved = sprite_path_for_name(name)
        _lookup_cache[key] = resolved
    return _lookup_cache[key]


def resolve_sprite(theme: Theme | None, name: str) -> str:
    """Like :func:`lookup_sprite`, but an unknown name becomes a placeholder."""
    resolved = lookup_sprite(theme, name)
    if resolved is not None:
        return resolved
    return placeholder(name, f"theme {None if theme is None else theme.name!r}")


def placeholder(name: str, context: str) -> str:
    """Warn once and return the magenta-checker name for unresolvable art —
    missing art must never crash a running sim."""
    if name not in _warned_missing:
        _warned_missing.add(name)
        print(f"[word_play] no sprite named {name!r} ({context}) — rendering a placeholder.", file=sys.stderr)
    return f"{MISSING_ROLE_PREFIX}{name}"


def apply_theme_defaults(renderable, theme: Theme | None) -> None:
    """Fill a Renderable's unset render fields from its behaviour and theme.

    Behaviour (light, smoke, floor, …) comes from the theme-independent
    :mod:`behaviours` registry. A theme then supplies per-name defaults — its
    lampposts glow, its stoves smoke, its "wall" autotiles. Explicit values
    always win, and ``sprite_path`` is never touched (it is resolved at draw
    time by :func:`resolve_sprite`).
    """
    from .behaviours import apply_behaviour

    apply_behaviour(renderable)
    name = renderable.sprite_path
    if theme is None or not name or not is_sprite_name(name):
        return
    glow_spec = theme.role_glow.get(name)
    if glow_spec is not None and renderable.glow is None:
        color, radius, strength = glow_spec
        renderable.glow = tuple(color)
        renderable.glow_radius = radius
        renderable.glow_strength = strength
    if name in theme.role_smoke:
        renderable.smoke = True
    if renderable.wall_set is None and name in theme.wall_roles:
        renderable.wall_set = theme.wall_set(name)
