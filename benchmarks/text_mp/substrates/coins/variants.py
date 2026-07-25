from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoinsVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 2
    observation_radius: int = 4

    @property
    def model_key(self) -> str:
        return "coins"

    @property
    def description(self) -> str:
        return f"Coins: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Collect coins of your own color for reward. Collecting the other player's coin "
            "costs them points. Cooperate by leaving their coins alone."
        )


OPEN_MAP = """
WWWWWWWWWWWWWWWWW
W..r...b...r...PW
W...............W
W...b.....r.....W
W...............W
WP..r...b...r...W
W...............W
W...b.....r.....W
W...............W
WWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "open": CoinsVariant(
        name="open",
        title="Open",
        tilemap=OPEN_MAP,
    ),
}
