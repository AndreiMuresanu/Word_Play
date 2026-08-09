from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FruitMarketVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 16
    observation_radius: int = 5

    @property
    def model_key(self) -> str:
        return "fruit_market"

    @property
    def description(self) -> str:
        return f"Fruit Market: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Harvest fruit by standing on trees. "
            "Eat your favorite fruit for +8 reward; eating your specialty fruit gives only +1. "
            "Set trade offers to swap fruit with nearby players. "
            "Keep your hunger low — going too long without eating drains stamina."
        )


# fmt: off
_OPEN_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
WtttttttttttttttttttttttttttttW
WtP..t..a.P..t.P..b..t..P..tttW
Wtt..P...t.....P.....t...P.tttW
Wt....RRRRRRRRRRRRRRRRR....tttW
WtP.tRtttttttttttttttttRtP.tttW
Wt...RtP...a.P.t.P.b..PR...tttW
WtP.tRtttttttttttttttttRtP.tttW
Wt....RRRRRRRRRRRRRRRRR....tttW
Wt..P..t.....P..t.....P..tttttW
Wt..P....b.P..t..P.a..t..P.tttW
WtttttttttttttttttttttttttttttW
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
"""

_CONCENTRIC_RIVERS_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
W.............................W
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
W.tttttttttttttttttttttttttttW
W.tttttttttttttttttttttttttttW
W.tttRRRRRRRRRRRRRRRRRRRRRtttW
W.tttRtttttttttttttttttttRtttW
W.tttRtttttttttttttttttttRtttW
W.tttRttRRRRRRRRRRRRRRRttRtttW
W.tttRttRtttttttttttttRttRtttW
W.tttRttRtttttttttttttRttRtttW
W.tttRttRttRRRRRRRRRttRttRtttW
W.tttRttRttRPtPtPtPRttRttRtttW
W.tttRttRttRtPtPtPtRttRttRtttW
W.tttRttRttRttPtPttRttRttRtttW
W.tttRttRttRtPtPtPtRttRttRtttW
W.tttRttRttRttPtPttRttRttRtttW
W.tttRttRttRtPtPtPtRttRttRtttW
W.tttRttRttRPtPtPtPRttRttRtttW
W.tttRttRttRRRRRRRRRttRttRtttW
W.tttRttRtttttttttttttRttRtttW
W.tttRttRtttttttttttttRttRtttW
W.tttRttRRRRRRRRRRRRRRRttRtttW
W.tttRtttttttttttttttttttRtttW
W.tttRtttttttttttttttttttRtttW
W.tttRRRRRRRRRRRRRRRRRRRRRtttW
W.tttttttttttttttttttttttttttW
W.tttttttttttttttttttttttttttW
W.tttttttttttttttttttttttttttW
W.............................W
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
"""
# fmt: on


VARIANTS: dict[str, FruitMarketVariant] = {
    "open": FruitMarketVariant(
        name="open",
        title="Open",
        tilemap=_OPEN_MAP,
    ),
    "concentric_rivers": FruitMarketVariant(
        name="concentric_rivers",
        title="Concentric Rivers",
        tilemap=_CONCENTRIC_RIVERS_MAP,
    ),
}
