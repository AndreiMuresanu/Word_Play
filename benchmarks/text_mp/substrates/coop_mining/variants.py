from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoopMiningVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 2
    observation_radius: int = 3

    @property
    def model_key(self) -> str:
        return "coop_mining"

    @property
    def description(self) -> str:
        return f"Coop Mining: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Mine iron ore solo for small reward. Mine gold ore together with another player "
            "for large reward — both must select the same gold vein in the same step. "
            "Coordinate on gold when nearby, fall back to iron otherwise."
        )


OPEN_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWWWWW
WOOOOOOOOOOOOOOOOOOOOOOOOOW
WOPOOOOOOOOOPOOOOOPOOOOOPOW
WOOOOOOOOWOOOOOOOOOOOOOOOOW
WOOOOOOOOWOOOOOOOOOOWOOOOOW
WOOOOOOOOWOOOOOOOOOOWOOOOOW
WOOOOOOOOWWWWWWWOOOOWOOOPOW
WOPOWWOOOOWOOOOOOOOOWOOOOOW
WOOOOOOOOOWOOPOOOOOOOOOOOOW
WOOOOOOOOOWOOOOOWWWOOOOOOOW
WOOOOOOOOOWOOOOOOOOOOOOOOOW
WOOOOOOOOOOOOOOOOOOOOOOOPOW
WOPOOOWWWOOOOOOWWWWWWWWOOOW
WOOWWWWOOOOOOOOOOOOOOOOOOOW
WOOOOOWOOOOWOOOOOPOOOOOOOOW
WOOOOOWOOOOWOOOOOOOOOOOOPOW
WOOOOOWOOOOOWOOOOOOOOWOOOOW
WOOOOOOWOOOOOWWWWOOOOWOOOOW
WOPOOOOOWOOOOOOOOOOOOWOOOOW
WOOOOOOOOWOOOPOOOOOOOOOOPOW
WOOOOOOOOOWOOOOOOOOWOOOOOOW
WOOOOWOOOOOOOOOOOOOWOOOOOOW
WOOOOWOOOOOOOOOWWWWWWWWOOOW
WOOOOWOOOOOOOOOOOOWOOOOOOOW
WOPOOOOOOPOOOOOOOPOOOOOOPOW
WOOOOOOOOOOOOOOOOOOOOOOOOOW
WWWWWWWWWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "open": CoopMiningVariant(
        name="open",
        title="Open",
        tilemap=OPEN_MAP,
    ),
}
