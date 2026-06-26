from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredatorPreyVariant:
    name: str
    title: str
    tilemap: str
    default_agent_count: int = 13
    default_predator_count: int = 5
    observation_radius: int = 5
    prompt: str = (
        "Predators catch prey for reward. Prey collect food while avoiding predators. "
        "Prey are safer in groups and predators cannot enter tall grass."
    )

    @property
    def model_key(self) -> str:
        return f"predator_prey__{self.name}"

    @property
    def description(self) -> str:
        return f"Predator Prey: {self.title}, adapted from Melting Pot."


OPEN_MAP = """
WWWWWWWWWWWWWWWWWWWWWWW
WWGGGGGGGGGGGGGGGGGGGWW
WGGGGGGGGGGGGGGGGGGGGGW
W.....................W
W..PPPPPPPPPPPPPPPPP..W
W..PCAAAAAAAAAACAAAP..W
W..PAAAAqAAACAAAAAAP..W
W.AAAAAAAAAAAAAAAAAAA.W
WCAAAAAAAAAAAAAAAAAAAAW
WAAAAAAAAAAAAAACAAAAAAW
WACAAAAAAAAAAAAAAAqAACW
W.AAAAAACAAAAAAAAACAA.W
W..PAAAAAAAqAAAAAAAP..W
W..PAAAAAAAACAAAAAAP..W
W..PPPPPPPPPPPPPPPPP..W
W.....................W
WGGGGGGGGGGGGGGGGGGGGGW
WWGGGGGGGGGGGGGGGGGGGWW
WWWWWWWWWWWWWWWWWWWWWWW
"""


ALLEY_HUNT_MAP = """
WWWWWWWWWWWWWWWWWWWWWWWW
WAA....................AAW
WA.........A..WW........AW
W..WWWWW..WW..WW..WWWWW..W
W..WWWWW..WW..WW..WWWWW..W
W....AWW..WWAAWW.........W
W..WWWWW..WWWWWW.A.WWWWW.W
W..WWWWW..WWWWWW.A.WWWWWAW
W..WWWWW...........WWWWWWW
W..WWWWW.PP....P....GGWWWW
W..........A....PP..GGGGGW
W.AA...P......A...PPGGGGGW
W..........A....PP..GGGGGW
W..WWWWW.......P....GGWWWW
W..WWWWW.PP........WWWWWWW
W..WWWWW..WWWWWW.A.WWWWWAW
W..WWWWW..WWWWWW.A.WWWWW.W
W....AWW..WWAAWW.........W
W..WWWWW..WW..WW..WWWWW..W
W..WWWWW..WW..WW..WWWWW..W
WA.........A..WW........AW
WAA....................AAW
WWWWWWWWWWWWWWWWWWWWWWWW
"""


ORCHARD_MAP = """
WWWWWWWWWWWWWWWWWWWWWWW
WWAA.P.PP..AWWA....ACWW
WA..AAAAAA.PWW..AAq..CW
WP.AACAAAAA....AAAAA..W
W.q.AAAAAA..CA.AAAAAA.W
WA...P....P...A......AW
WAA..AAA............AAW
WWW..AAA..WWWWPPPACWWWW
WWW...A.P.WWWWWWWWWWWWW
WPP...A.P...WWWWWWWWW.W
W.....A......PP.......W
W.GGGGGGGG...P.C...C..W
W.GGGGGGGGGG.....C....W
W...GGGGGGGG...C...C..W
W..GGGGGGGG......C...PW
W..GGGGGGGGGG..C...C..W
W....GGGGGGGG....C.q..W
WW...................WW
WWWWWWWWWWWWWWWWWWWWWWW
"""


RANDOM_FOREST_MAP = """
WWWWWWWWWWWWWWWWWWWWWWW
WWPCPPPPPPPCPPPPPPPCPWW
WPPPPPPPPPPPPPPPPPPPPPW
W....G.G..GGG..G.G....W
W.G..G.GG..C..GG.G..G.W
W.GC.G..GGGGGGG..G.CG.W
W......CG.....GC......W
WG.GGGGGGqqqqqGGGGGG.GW
WG......qqqqqqq......GW
WC.GGC..qqqCqqq..CGG.CW
WG......qqqqqqq......GW
WG.GGGGGGqqqqqGGGGGG.GW
W......CG.....GC......W
W.GC.G..GGGGGGG..G.CG.W
W.G..G.GG..C..GG.G..G.W
W....G.G..GGG..G.G....W
WPPPPPPPPPPPPPPPPPPPPPW
WWPCPPPPPPPCPPPPPPPCPWW
WWWWWWWWWWWWWWWWWWWWWWW
"""


VARIANTS = {
    "open": PredatorPreyVariant(
        name="open",
        title="Open",
        tilemap=OPEN_MAP,
        default_predator_count=3,
        prompt=(
            "Predators catch prey for reward. Prey collect apples and acorns while avoiding predators. "
            "Use the open space carefully and watch nearby roles."
        ),
    ),
    "alley_hunt": PredatorPreyVariant(
        name="alley_hunt",
        title="Alley Hunt",
        tilemap=ALLEY_HUNT_MAP,
        prompt=(
            "Predators catch prey for reward. Prey collect apples and stay clear of predators. "
            "Walls create alleys, so routes and chokepoints matter."
        ),
    ),
    "orchard": PredatorPreyVariant(
        name="orchard",
        title="Orchard",
        tilemap=ORCHARD_MAP,
        prompt=(
            "Predators hunt prey. Prey collect apples and acorns while using the orchard and grass for safety. "
            "Predators should coordinate around cover."
        ),
    ),
    "random_forest": PredatorPreyVariant(
        name="random_forest",
        title="Random Forest",
        tilemap=RANDOM_FOREST_MAP,
        prompt=(
            "Predators catch prey. Prey gather food and use grass cover to avoid being caught. "
            "Pay attention to nearby food, cover, and opponents."
        ),
    ),
}
