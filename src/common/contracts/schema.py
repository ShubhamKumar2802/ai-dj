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
    # Seconds per bar of track A — the unit `length_bars` and every
    # `Envelope.bar_offset` are counted in. Required, no default: without it the
    # renderer cannot convert either into samples (edge_builder spec v2 §6).
    bar_seconds: float

    rate_a: float
    rate_b: float

    gain_db_a: float
    gain_db_b: float

    envelopes: list[Envelope]
