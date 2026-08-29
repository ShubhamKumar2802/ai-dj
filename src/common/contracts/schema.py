from dataclasses import dataclass
from typing import Any, Literal


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


@dataclass
class TrackRef:
    id: str
    path: str

    # This track's own opening point. Consulted ONLY when it has no preceding
    # junction — i.e. the opener (D24's free cue-in). None = from 0.0.
    cue_in: float | None
    # This track's own closing point. Consulted ONLY when it has no following
    # junction — i.e. the closer (D24). None = to the natural end.
    cue_out: float | None
    # D24's fallback: `closer_fade_bars` on the last track when it has no
    # `outro_start` cue, so the renderer fades to silence instead of stopping
    # dead. None = no fade. Always None on every non-closer TrackRef.
    fade_out_bars: int | None

    # Carried through from Track. path_search never reads it — it exists so the
    # renderer (which receives only the MixPlan, never Track[]) can compute
    # set-wide LUFS gain (path_search spec §2).
    lufs_integrated: float


@dataclass
class MixPlanConfig:
    # K as requested (PathSearchConfig.target_track_count). The ACHIEVED count is
    # len(MixPlan.tracks), which may be smaller (D21).
    track_count: int
    energy_arc: str
    seed_track: str | None

    # dataclasses.asdict(PathSearchConfig) — design-v3 §5.2's "weights".
    path_search: dict[str, Any]
    # dataclasses.asdict(EdgeBuilderConfig) when the caller passes `edge_config`;
    # design-v3 §5.2's "tier_penalties". None otherwise (path_search spec Q10).
    edge_builder: dict[str, Any] | None


@dataclass
class MixPlan:
    config: MixPlanConfig
    # In play order; tracks[0] opens, tracks[-1] closes.
    tracks: list[TrackRef]
    # len == len(tracks) - 1. junctions[i] joins tracks[i] -> tracks[i+1], copied
    # verbatim from ScoredEdge.plan (D4 — stored, never recomputed).
    junctions: list[Junction]
