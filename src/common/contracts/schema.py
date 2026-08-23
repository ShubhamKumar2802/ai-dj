from dataclasses import dataclass
from typing import Literal


@dataclass
class Envelope:
    target: Literal["low", "mid", "high", "crossfader"]
    side: Literal["a", "b"]
    breakpoints: list[tuple[float, float]]


@dataclass
class Junction:
    from_track: str
    to_track: str

    cue_out: float
    cue_in: float

    strategy_tier: int

    ramp_bars: int
    length_bars: int

    rate_a: float
    rate_b: float

    gain_db_a: float
    gain_db_b: float

    envelopes: list[Envelope]
