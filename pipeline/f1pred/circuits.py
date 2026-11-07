"""Hand-maintained circuit traits that the timing data can't tell us.

overtaking: 1 = easy to pass (long straights, DRS works) ... 5 = nearly impossible (Monaco).
street: 1 for street or semi-street layouts, where walls punish mistakes and safety cars are common.
These are judgment calls; the model learns how much they matter. Unknown circuits get neutral values.
"""

CIRCUITS: dict[str, dict[str, float]] = {
    "albert_park": {"overtaking": 3, "street": 1},
    "americas": {"overtaking": 2, "street": 0},
    "bahrain": {"overtaking": 1, "street": 0},
    "baku": {"overtaking": 1, "street": 1},
    "catalunya": {"overtaking": 3, "street": 0},
    "hockenheimring": {"overtaking": 2, "street": 0},
    "hungaroring": {"overtaking": 4, "street": 0},
    "imola": {"overtaking": 4, "street": 0},
    "interlagos": {"overtaking": 2, "street": 0},
    "istanbul": {"overtaking": 2, "street": 0},
    "jeddah": {"overtaking": 2, "street": 1},
    "losail": {"overtaking": 3, "street": 0},
    "madring": {"overtaking": 3, "street": 1},
    "marina_bay": {"overtaking": 4, "street": 1},
    "miami": {"overtaking": 3, "street": 1},
    "monaco": {"overtaking": 5, "street": 1},
    "monza": {"overtaking": 2, "street": 0},
    "mugello": {"overtaking": 4, "street": 0},
    "nurburgring": {"overtaking": 3, "street": 0},
    "portimao": {"overtaking": 3, "street": 0},
    "red_bull_ring": {"overtaking": 2, "street": 0},
    "ricard": {"overtaking": 3, "street": 0},
    "rodriguez": {"overtaking": 3, "street": 0},
    "sepang": {"overtaking": 2, "street": 0},
    "shanghai": {"overtaking": 2, "street": 0},
    "silverstone": {"overtaking": 2, "street": 0},
    "sochi": {"overtaking": 3, "street": 1},
    "spa": {"overtaking": 1, "street": 0},
    "suzuka": {"overtaking": 3, "street": 0},
    "vegas": {"overtaking": 1, "street": 1},
    "villeneuve": {"overtaking": 2, "street": 1},
    "yas_marina": {"overtaking": 3, "street": 0},
    "zandvoort": {"overtaking": 4, "street": 0},
}

_DEFAULT = {"overtaking": 3, "street": 0}


def traits(circuit_id: str) -> dict[str, float]:
    return CIRCUITS.get(circuit_id, _DEFAULT)
