import pytest

from experiments.llm_camelot_sequencer.mix_builder import build_camelot_mix_plan
from ingestion.cue_derivation.schema import Cue


def test_builds_a_plan_with_grid_start_entries_and_chorus_end_exits(make_track, make_labels):
    tracks = [
        make_track(id="a", grid_start=4.0, bpm=120.0, cue_outs=[]),
        make_track(id="b", grid_start=6.0, bpm=120.0, cue_outs=[]),
        make_track(id="c", grid_start=5.0, bpm=120.0, cue_outs=[Cue(100.0, "outro_start", 0.9)]),
    ]
    tracks_by_id = {t.id: t for t in tracks}
    labels_by_id = {
        "a": make_labels(chorus1_start=30.0, chorus1_end=60.0),
        "b": make_labels(chorus1_start=30.0, chorus1_end=60.0),
        "c": make_labels(chorus1_start=30.0, chorus1_end=60.0),
    }

    plan = build_camelot_mix_plan(["a", "b", "c"], tracks_by_id, labels_by_id)

    assert len(plan.tracks) == 3
    assert len(plan.junctions) == 2

    # Opener: cue_in = its own grid_start; cue_out left to the first junction.
    assert plan.tracks[0].cue_in == 4.0
    assert plan.tracks[0].cue_out is None

    # Interior track: both sides authoritative on the flanking junctions.
    assert plan.tracks[1].cue_in is None
    assert plan.tracks[1].cue_out is None

    # Closer: cue_out comes from relax_closer() (an outro_start cue exists here
    # -> plays to its natural end, per boundaries.relax_closer's first branch).
    assert plan.tracks[2].cue_in is None
    assert plan.tracks[2].cue_out is None
    assert plan.tracks[2].fade_out_bars is None

    # Junctions carry the LLM's chorus1_end / the next track's grid_start.
    assert plan.junctions[0].cue_out == 60.0  # a's chorus1_end
    assert plan.junctions[0].cue_in == 6.0  # b's grid_start
    assert plan.junctions[1].cue_out == 60.0  # b's chorus1_end
    assert plan.junctions[1].cue_in == 5.0  # c's grid_start
    assert all(j.strategy_tier == 3 for j in plan.junctions)


def test_raises_on_an_interior_segment_shorter_than_min_play_seconds(make_track, make_labels):
    tracks = [
        make_track(id="a", grid_start=4.0),
        # b's own window (its grid_start to its chorus1_end) is fine, but its
        # incoming-to-outgoing SPAN as an interior track (junctions[0].cue_in
        # -> junctions[1].cue_out) is forced too short here.
        make_track(id="b", grid_start=58.0),
        make_track(id="c", grid_start=4.0),
    ]
    tracks_by_id = {t.id: t for t in tracks}
    labels_by_id = {
        "a": make_labels(chorus1_start=30.0, chorus1_end=60.0),
        "b": make_labels(chorus1_start=59.0, chorus1_end=60.0),  # 60 - 58 = 2.0s span
        "c": make_labels(chorus1_start=30.0, chorus1_end=60.0),
    }

    with pytest.raises(ValueError, match="min_play_seconds"):
        build_camelot_mix_plan(["a", "b", "c"], tracks_by_id, labels_by_id, min_play_seconds=8.0)
