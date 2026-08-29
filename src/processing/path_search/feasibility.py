from common.contracts.schema import Junction


def segment_span(prev_cue_in: float, next_cue_out: float) -> float:
    """Play duration of the track sitting between two junctions.

    For an interior track ``j`` on a path, this is ``junctions[j].cue_out -
    junctions[j-1].cue_in`` (spec §3).
    """
    return next_cue_out - prev_cue_in


def extension_is_feasible(
    prev_cue_in: float | None,
    next_cue_out: float,
    min_play_seconds: float,
) -> bool:
    """O(1) check for appending one edge to a partial path (spec §3).

    ``prev_cue_in`` is the frontier track's incoming ``cue_in`` — ``None`` for a
    length-1 path, whose single track is not yet interior and so imposes no
    constraint. ``next_cue_out`` is the new edge's ``cue_out`` (the frontier
    track's exit). Appending the new edge makes the frontier track interior, with
    a known cue-in and cue-out for the first time.

    This is the structural gap nothing upstream can close: edge_builder scores
    every pair "as if both sat mid-set" with no notion of path, so B's cue-in on
    ``A->B`` and its cue-out on ``B->C`` are chosen in mutual ignorance and can
    land out of order — a negative play duration, emitted silently. A
    negative-length segment is not a musical judgement (D10), so this is a hard
    constraint, not a scored cost.
    """
    if prev_cue_in is None:
        return True
    return segment_span(prev_cue_in, next_cue_out) >= min_play_seconds


def path_is_feasible(junctions: list[Junction], min_play_seconds: float) -> bool:
    """Full O(K) scan — every interior track's span clears ``min_play_seconds``.

    The beam uses the incremental ``extension_is_feasible`` form; this exists for
    tests and as an optional defensive assert once a whole path is built.
    """
    return all(
        segment_span(junctions[k].cue_in, junctions[k + 1].cue_out) >= min_play_seconds
        for k in range(len(junctions) - 1)
    )
