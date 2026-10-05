"""A library-wide sprite name index: plain words resolve to real art.

Walks ``sprite_library/src`` once and maps normalized filename stems to
repo-relative paths, so an entity can say ``Renderable(sprite_path="sheep")``
and get matching art without knowing the folder layout. Themes take
precedence; the index is the fallback before the magenta placeholder.

No pygame dependency — pure filesystem.
"""

from __future__ import annotations


# Stem-conflict preference: characters and items first, generated packs last.
_ROOT_PRIORITY = (
    "src/characters/",
    "src/items/",
    "src/world_tiles/",
    "src/ui/",
    "src/generated/",
)

# sibling-convention suffixes that are variants of a base file, not standalone art
_SKIP_SUFFIXES = ("_back", "_glow")

_INDEX: dict[str, str] | None = None


def _priority(rel: str) -> tuple[int, str]:
    for rank, prefix in enumerate(_ROOT_PRIORITY):
        if rel.startswith(prefix):
            return (rank, rel)
    return (len(_ROOT_PRIORITY), rel)


def _normalize_stem(stem: str) -> str:
    stem = stem.lower()
    while stem and stem[-1] == ")":          # drop "(1)" duplicate suffixes
        stem = stem[: stem.rfind("(")] if "(" in stem else stem[:-1]
    if stem.endswith("_2"):
        stem = stem[:-2].rstrip("_")
    return stem.strip("_")


def _build_index() -> dict[str, str]:
    from .themes import _project_root

    library = _project_root() / "sprite_library"
    index: dict[str, str] = {}
    if not library.is_dir():
        return index

    entries: list[tuple[tuple[int, str], str, str]] = []
    for path in (library / "src").rglob("*.png"):
        rel = path.relative_to(library).as_posix()
        stem = _normalize_stem(path.stem)
        if not stem or any(stem.endswith(suffix) for suffix in _SKIP_SUFFIXES):
            continue
        entries.append((_priority(rel), stem, f"sprite_library/{rel}"))

    for _, stem, sprite_path in sorted(entries, key=lambda e: e[0]):
        index.setdefault(stem, sprite_path)
    return index


def sprite_index() -> dict[str, str]:
    """The lazily built name -> path index (built once per process)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def sprite_path_for_name(name: str) -> str | None:
    """Sprite path for a plain-word name: exact normalized stem, then singular."""
    index = sprite_index()
    key = name.strip().lower().replace(" ", "_")
    for candidate in (key, key.removesuffix("s")):
        if candidate and candidate in index:
            return index[candidate]
    return None
