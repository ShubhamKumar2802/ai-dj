from typing import Literal

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.schema import Cue, PhraseBoundary
from ingestion.feature_extractor.schema import RawFeatures

# Heuristic-derived (§6); spec gives no confidence formula for hook_in/hook_exit cues.
_HOOK_CUE_CONFIDENCE = 0.5

# time_boxed is the least-informed, purely mechanical fallback; spec gives no
# confidence formula for it either.
_FALLBACK_CUE_CONFIDENCE = 0.3


def bars_to_seconds(bars: float, raw: RawFeatures) -> float:
    return bars * raw.beats_per_bar * 60.0 / raw.bpm


def _time_boxed_cue(
    raw: RawFeatures,
    reference_position: float,
    phrase_grid: list[PhraseBoundary],
    config: CueDerivationConfig,
) -> Cue | None:
    """First phrase boundary at/after config.time_box_bars bars past
    reference_position — spec §7's guaranteed cue-out fallback. Spec's own
    "needs only phrase_grid[]" note (not vocal_band_energy[] too) confirms
    "first phrase boundary after N bars" is the literal selection rule, not
    a separate vocal-minimizing search over several candidates."""
    target = reference_position + bars_to_seconds(config.time_box_bars, raw)
    for boundary in phrase_grid:
        if boundary.position >= target:
            return Cue(
                position=boundary.position,
                kind="time_boxed",
                confidence=_FALLBACK_CUE_CONFIDENCE,
            )
    return None


def emit_cues(
    raw: RawFeatures,
    grid_start: float,
    free_intro_end: float,
    structure_template: Literal["edm", "film", "unknown"],
    hook_in: float | None,
    hook_exit: float | None,
    phrase_grid: list[PhraseBoundary],
    config: CueDerivationConfig,
) -> tuple[list[Cue], list[Cue]]:
    """Returns (cue_ins, cue_outs) — spec §7's preference orders (amended).

    Emits every qualifying candidate per side, in preference order, not a
    single winner — the (out-of-scope) edge builder searches over cue-point
    combinations (CLAUDE.md's own architecture description), so this module
    hands over candidates rather than deciding for it. outro_start never
    fires (§7 amendment — no v1 detector exists for it).
    """
    cue_ins: list[Cue] = []

    if structure_template == "edm":
        # Reuses free_intro_end (grid_origin.py already computed this exact
        # comparison, §3) instead of re-deriving "riser_candidates[0].start_time
        # < grid_start" independently — keeps the two checks from silently
        # drifting apart if grid_origin.py's riser-selection rule ever changes.
        # The non-emptiness guard stays: it's a genuinely different condition,
        # not a duplicate, and protects against an inconsistent direct call
        # (free_intro_end < grid_start with no riser present).
        if raw.riser_candidates and free_intro_end < grid_start:
            riser = raw.riser_candidates[0]
            cue_ins.append(
                Cue(position=free_intro_end, kind="riser_start", confidence=riser.confidence)
            )
        else:
            cue_ins.append(
                Cue(position=free_intro_end, kind="intro_end", confidence=raw.downbeat_confidence)
            )
    elif hook_in is not None:
        cue_ins.append(Cue(position=hook_in, kind="hook_in", confidence=_HOOK_CUE_CONFIDENCE))

    # Guaranteed fallback (§7) — always emitted, even when a branch above also fired.
    cue_ins.append(
        Cue(position=grid_start, kind="first_downbeat", confidence=raw.downbeat_confidence)
    )

    # Hard constraint on cue_ins, applied now — before cue_ins[0] is used
    # below as time_boxed's anchor, so a filtered-out cue-in can never
    # silently determine the emitted cue-out (§1, §7, D9/D10: no cue before
    # grid_start, except riser_start, which precedes grid_start by
    # construction — grid_start is the first downbeat).
    cue_ins = [c for c in cue_ins if c.position >= grid_start or c.kind == "riser_start"]

    cue_outs: list[Cue] = []
    if hook_exit is not None:
        cue_outs.append(Cue(position=hook_exit, kind="hook_exit", confidence=_HOOK_CUE_CONFIDENCE))

    # time_boxed is anchored to this module's own top-preference *surviving*
    # cue-in candidate (cue_ins[0], always present post-filter) — spec's
    # formula assumes a singular "cue-in" reference point, which predates
    # this module's multi-candidate emission design.
    time_boxed = _time_boxed_cue(raw, cue_ins[0].position, phrase_grid, config)
    if time_boxed is not None:
        cue_outs.append(time_boxed)

    cue_outs = [c for c in cue_outs if c.position >= grid_start or c.kind == "riser_start"]

    return cue_ins, cue_outs
