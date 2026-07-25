from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GiftRefimentsVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 6
    observation_radius: int = 5

    @property
    def model_key(self) -> str:
        return "gift_refinements"

    @property
    def description(self) -> str:
        return f"Gift Refinements: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Pick up raw tokens from the ground. Gift your rawest token to a nearby player "
            "for +10 reward — they receive 5 upgraded tokens. "
            "Consume all your tokens when you can't find a gifting partner."
        )


OPEN_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWWWWW
WTTTTTTTTTTTTTTTTTTTTTTTTTW
WTPTTTTTTTTTPTTTTTPTTTTTPTW
WTTTTTTTTWTTTTTTTTTTTTTTTTW
WTTTTTTTTWTTTTTTTTTTWTTTTTW
WTTTTTTTTWTTTTTTTTTTWTTTTTW
WTTTTTTTTWWWWWWWTTTTWTTTPTW
WTPTWWTTTTWTTTTTTTTTWTTTTTW
WTTTTTTTTTWTTPTTTTTTTTTTTTW
WTTTTTTTTTWTTTTTWWWTTTTTTTW
WTTTTTTTTTWTTTTTTTTTTTTTTTW
WTTTTTTTTTTTTTTTTTTTTTTTPTW
WTPTTTWWWTTTTTTWWWWWWWWTTTW
WTTWWWWTTTTTTTTTTTTTTTTTTTW
WTTTTTWTTTTWTTTTTPTTTTTTTTW
WTTTTTWTTTTWTTTTTTTTTTTTPTW
WTTTTTWTTTTTWTTTTTTTTWTTTTW
WTTTTTTWTTTTTWWWWTTTTWTTTTW
WTPTTTTTWTTTTTTTTTTTTWTTTTW
WTTTTTTTTWTTTPTTTTTTTTTTPTW
WTTTTTTTTTWTTTTTTTTWTTTTTTW
WTTTTWTTTTTTTTTTTTTWTTTTTTW
WTTTTWTTTTTTTTTWWWWWWWWTTTW
WTTTTWTTTTTTTTTTTTWTTTTTTTW
WTPTTTTTTPTTTTTTTPTTTTTTPTW
WTTTTTTTTTTTTTTTTTTTTTTTTTW
WWWWWWWWWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "open": GiftRefimentsVariant(
        name="open",
        title="Open",
        tilemap=OPEN_MAP,
    ),
}
