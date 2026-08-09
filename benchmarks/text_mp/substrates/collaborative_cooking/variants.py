from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollaborativeCookingVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 2
    observation_radius: int = 4

    @property
    def model_key(self) -> str:
        return "collaborative_cooking"

    @property
    def description(self) -> str:
        return f"Collaborative Cooking: {self.title}, adapted from Melting Pot."

    @property
    def prompt(self) -> str:
        return (
            "Make and deliver soup for shared reward. "
            "Take a Tomato from the Tomato Source and Load it into a Cooking Pot three times. "
            "Once the pot shows ready, take a Dish and use it to plate the soup. "
            "Deliver the held soup to the Delivery Window. "
            "Your inventory holds one item — use Counters or Drop to make room."
        )


# fmt: off
_OPEN = """
WWWWWWWWWWWW
W.PO..D..P.W
W..........W
W...#CPT...W
W..........W
W....#.....W
WWWWWWWWWWWW
"""

_CRAMPED = """
WW##C##WW
WWOP.POWW
WW#...#WW
WW#D#T#WW
WWWWWWWWW
"""

_ASYMMETRIC = """
#########
O.#T#O#.T
#.P.C.P.#
#...C...#
###D#D###
"""

_CIRCUIT = """
W###CC###
W#P.....#
WD.####.T
W#.....P#
W###OO###
"""

_CROWDED = """
###D###O#O###
#P..P#.P...##
#....#...P.##
C.P..#P....##
#....#P.....T
C...P#...P.##
#.P..#..P..##
#P.........##
#############
"""

_FIGURE_EIGHT = """
################
####C#C##C#C####
#.P..........P.#
##.##########.##
#....P...P.....#
##.##########.##
#....P...P.....#
###.#ODTTOD#.###
################
"""

_FORCED = """
WW###C#WW
WWO.#PCWW
WWOP#.#WW
WWD.#.#WW
WW###T#WW
"""

_RING = """
WW###C#WW
WW#...CWW
WWDP#.#WW
WWO.P.#WW
WW#OT##WW
"""
# fmt: on


VARIANTS: dict[str, CollaborativeCookingVariant] = {
    "open": CollaborativeCookingVariant(
        name="open", title="Open", tilemap=_OPEN, default_agent_count=2
    ),
    "cramped": CollaborativeCookingVariant(
        name="cramped", title="Cramped", tilemap=_CRAMPED, default_agent_count=2
    ),
    "asymmetric": CollaborativeCookingVariant(
        name="asymmetric", title="Asymmetric", tilemap=_ASYMMETRIC, default_agent_count=2
    ),
    "circuit": CollaborativeCookingVariant(
        name="circuit", title="Circuit", tilemap=_CIRCUIT, default_agent_count=2
    ),
    "crowded": CollaborativeCookingVariant(
        name="crowded", title="Crowded", tilemap=_CROWDED, default_agent_count=9,
        observation_radius=5,
    ),
    "figure_eight": CollaborativeCookingVariant(
        name="figure_eight", title="Figure Eight", tilemap=_FIGURE_EIGHT,
        default_agent_count=6, observation_radius=5,
    ),
    "forced": CollaborativeCookingVariant(
        name="forced", title="Forced", tilemap=_FORCED, default_agent_count=2
    ),
    "ring": CollaborativeCookingVariant(
        name="ring", title="Ring", tilemap=_RING, default_agent_count=2
    ),
}
