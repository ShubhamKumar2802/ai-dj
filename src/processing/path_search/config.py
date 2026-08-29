from dataclasses import dataclass


@dataclass
class PathSearchConfig:
    # K — spec §0's "~15 tracks in ~17 minutes". The ACHIEVED count may be lower
    # (a dead-ended pool), which is a degradation to report, not an error.
    target_track_count: int = 15
    # D3's "top ~50" partial sequences (Q7).
    beam_width: int = 50
    # Track.id pinned at position 0, if any (D1, Q8). None = free choice of opener.
    seed_track: str | None = None
    # Feasibility floor: an interior track playing for less than this is a glitch
    # in the mix, not a member of the set (spec §3). ~4 bars at 120 BPM.
    min_play_seconds: float = 8.0

    # "arc" (builds, peaks, comes down) | "rise" (monotonic build) | "flat".
    energy_arc: str = "arc"
    arc_peak_position: float = 0.70
    arc_start_level: float = 0.35
    arc_end_level: float = 0.60

    # The four path-level weights, expressed in EDGE-COST units (spec §4's scale
    # fix): Sigma edge_costs lands at ~15-25 over K-1 edges while each path term
    # caps at 1.0, so w_arc = 8.0 reads as "a wholly wrong energy arc costs as
    # much as eight typical junctions". Every value here is provisional (D26, Q5).
    w_arc: float = 8.0  # lambda
    w_diversity: float = 4.0  # mu
    w_familiarity: float = 8.0  # nu — inert in v1 (no familiarity scores exist yet)
    w_boundary: float = 4.0  # beta

    diversity_bpm_target_std: float = 8.0
    # D24's fade fallback when the closer has no outro_start cue (spec §8).
    closer_fade_bars: int = 4
    # Number of runner-up complete paths to return; clamped to beam_width.
    n_alternatives: int = 0
