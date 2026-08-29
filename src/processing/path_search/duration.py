from common.contracts.schema import Junction, TrackRef
from ingestion.orchestrator.schema import Track


def overlap_seconds(junction: Junction) -> float:
    """Seconds the two tracks play together across this junction:
    ``length_bars * bar_seconds`` (edge_builder v2 §6). Tier 3 has
    ``length_bars == 0`` and degenerates to a splice, so its overlap is ``0``."""
    return junction.length_bars * junction.bar_seconds


def estimated_duration_s(
    track_refs: list[TrackRef],
    junctions: list[Junction],
    tracks_by_id: dict[str, Track],
) -> float:
    """``Sigma spans - Sigma overlaps`` (spec §10).

    D21 is explicit that this is logged, never constrained — "15 tracks landing at
    40 minutes against a ~17-minute reference means the time-boxed cut is
    mis-sized: a signal, not a constraint." It is an estimate: the renderer's
    sample math is authoritative, and tier 2's ``rate_b`` time-stretch shifts B's
    real duration in a way this arithmetic does not model.

    Runs after ``build_mix_plan``, so it reads the post-D24 ``TrackRef``s: the
    opener's ``cue_in`` is ``None`` (=> ``0.0``) and the closer's ``cue_out`` is
    ``None`` when it plays to its natural end (=> ``Track.duration``).
    """
    if len(track_refs) == 1:
        opener = track_refs[0]
        end = opener.cue_out if opener.cue_out is not None else tracks_by_id[opener.id].duration
        return end - (opener.cue_in or 0.0)

    spans = 0.0
    spans += junctions[0].cue_out - (track_refs[0].cue_in or 0.0)
    for i in range(1, len(track_refs) - 1):
        spans += junctions[i].cue_out - junctions[i - 1].cue_in
    closer = track_refs[-1]
    closer_end = closer.cue_out if closer.cue_out is not None else tracks_by_id[closer.id].duration
    spans += closer_end - junctions[-1].cue_in

    overlaps = sum(overlap_seconds(j) for j in junctions)
    return spans - overlaps
