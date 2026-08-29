from collections.abc import Sequence

import numpy as np

from ingestion.orchestrator.schema import Track

_GOOD_OPENER_CUE_KINDS = frozenset({"riser_start", "intro_end"})
_GOOD_CLOSER_CUE_KIND = "outro_start"


def opener_cost(track: Track) -> float:
    """How well this track works as the set's first track — D24's stated
    preference, applied as a scored cost per D10 (spec §8).

    ``0.0`` a free-time or riser intro survives intact; ``0.5`` there is at least
    some real intro to relax into; ``1.0`` otherwise.
    """
    if any(cue.kind in _GOOD_OPENER_CUE_KINDS for cue in track.cue_ins):
        return 0.0
    if track.free_intro_end > track.grid_start:
        return 0.5
    return 1.0


def closer_cost(track: Track) -> float:
    """How well this track works as the set's last track (spec §8).

    ``0.0`` it has an ``outro_start`` cue to end on; ``1.0`` otherwise — the
    4-bar-fade fallback. ``cue_derivation`` never emits ``outro_start`` in v1, so
    this is a constant ``1.0`` and only the opener half of the boundary term is
    live. A constant term cannot distort ranking, so it is inert, not wrong.
    """
    if any(cue.kind == _GOOD_CLOSER_CUE_KIND for cue in track.cue_outs):
        return 0.0
    return 1.0


def boundary_cost(opener: Track, closer: Track) -> float:
    """``mean(opener_cost(path[0]), closer_cost(path[-1]))`` — the beta term (spec §4)."""
    return 0.5 * (opener_cost(opener) + closer_cost(closer))


def opener_cost_array(pool: Sequence[Track]) -> np.ndarray:
    """Pool-aligned ``opener_cost`` — the beam indexes this by the frontier path's
    first track each rescore (spec §11 step 2)."""
    return np.array([opener_cost(t) for t in pool], dtype=float)


def closer_cost_array(pool: Sequence[Track]) -> np.ndarray:
    """Pool-aligned ``closer_cost`` — indexed by the frontier track each step,
    which is only the *real* closer once a path is complete (spec Q13; moot in v1
    while ``closer_cost`` is constant)."""
    return np.array([closer_cost(t) for t in pool], dtype=float)


def relax_closer(track: Track, closer_fade_bars: int) -> tuple[float | None, int | None]:
    """D24's relaxation of the closer's one unconstrained side (spec §8).

    Returns ``(TrackRef.cue_out, TrackRef.fade_out_bars)`` for the last track:

    - has an ``outro_start`` cue -> ``(None, None)`` — plays to its natural end.
    - else, has ``cue_outs`` -> ``(cue_outs[0].position, closer_fade_bars)`` —
      D24's stated fallback: time-box as normal, then fade to silence.
    - else, no ``cue_outs`` at all -> ``(None, closer_fade_bars)`` — nothing to
      time-box on, so run to the natural end and still fade (documented gap-fill;
      spec §8's table assumes a first ``cue_outs`` entry exists).

    The opener needs no companion function: D24 only sets ``cue_in = None`` on it,
    which is what ``plan_builder`` writes for every non-closer ``TrackRef`` anyway.
    """
    if any(cue.kind == _GOOD_CLOSER_CUE_KIND for cue in track.cue_outs):
        return None, None
    if track.cue_outs:
        return track.cue_outs[0].position, closer_fade_bars
    return None, closer_fade_bars
