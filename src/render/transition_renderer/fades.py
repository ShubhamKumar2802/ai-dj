import numpy as np

# Anti-click hygiene against a gain discontinuity at a splice, not a musical
# "strategy" choice like the tier ladder (spec §5). Linear, not equal-power:
# over 5 ms the curve shape is inaudible, and the two fades this is used for
# never overlap, so there is no perceived-loudness dip to correct for.
# FADE_MS is an unvalidated guess pending an ear check against real output
# (spec §10 Q1).
FADE_MS = 5


def linear_edge_fade(segment: np.ndarray, sample_rate: int, *, fade_in: bool) -> np.ndarray:
    """Ramp the first (``fade_in``) or last (``fade_out``) ``FADE_MS`` of a
    ``(n_samples, 2)`` segment linearly between silence and unity. Returns a
    copy; the input is not mutated.

    Promoted from a private helper inside ``strategies/cut_on_the_one.py`` to
    this shared module (spec §5.1, 2026-09-17 amendment) — ``playlist_renderer``
    Milestone B's body-slicer needs the exact same anti-click treatment at
    every track-body boundary, not just at a tier-3 junction. Behavior is
    unchanged from the original private version.
    """
    n_fade = min(round(FADE_MS / 1000 * sample_rate), len(segment))
    if n_fade == 0:
        return segment.copy()
    ramp = np.linspace(0.0, 1.0, n_fade, dtype=segment.dtype)
    out = segment.copy()
    if fade_in:
        out[:n_fade] *= ramp[:, None]
    else:
        out[-n_fade:] *= ramp[::-1, None]
    return out
