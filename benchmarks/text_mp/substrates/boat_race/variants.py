from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoatRaceVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 6
    observation_radius: int = 4
    race_count: int = 8
    prompt: str = (
        "Pair up, board or move near the boat area, and coordinate Paddle actions. "
        "Two players paddling in the same step advances race progress. "
        "Flail can sometimes help, but coordinated paddling is better."
    )

    @property
    def model_key(self) -> str:
        return "boat_race" if self.name == "standard" else f"boat_race__{self.name}"

    @property
    def description(self) -> str:
        return f"Boat Race: {self.title}, adapted from Melting Pot."


BOAT_RACE_MAP = r"""
WWWWWWWWWWWWWWWWWWWWWWWWWW
W........................W
W........................W
W........................W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W........................W
W......S..SS..SS..S......W
W......SBBSSBBSSBBS......W
W......S..SS..SS..S......W
~~~~~~~~gg~~gg~~gg~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~AA~~AA~~AA~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~AA~~AA~~AA~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~AA~~AA~~AA~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~{{~~{{~~{{~~~~~~~~
~~~~~~~~AA~~AA~~AA~~~~~~~~
~~~~~~~~bb~~bb~~bb~~~~~~~~
~~~~~~~ossoossoosso~~~~~~~
W......SbbSSbbSSbbS......W
W......SBBSSBBSSBBS......W
W......S..SS..SS..S......W
W........................W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W......AAAAAAAAAAAA......W
W........................W
W....________________....W
W....________________....W
WWWWWWWWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "standard": BoatRaceVariant(
        name="standard",
        title="Standard",
        tilemap=BOAT_RACE_MAP,
    ),
    "eight_races": BoatRaceVariant(
        name="eight_races",
        title="Eight Races",
        tilemap=BOAT_RACE_MAP,
        prompt=(
            "Coordinate Paddle actions with another player to advance the race. "
            "Eight race-progress events are needed. Flail only when coordination fails."
        ),
    ),
}
