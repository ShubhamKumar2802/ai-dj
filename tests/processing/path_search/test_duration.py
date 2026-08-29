import pytest

from processing.path_search.duration import estimated_duration_s, overlap_seconds


def test_overlap_seconds(make_junction):
    assert overlap_seconds(make_junction(length_bars=0, bar_seconds=2.0)) == 0.0
    assert overlap_seconds(make_junction(length_bars=16, bar_seconds=2.0)) == pytest.approx(32.0)


def test_two_track_plan_spans_minus_overlaps(make_track, make_track_ref, make_junction):
    tracks_by_id = {"A": make_track(id="A"), "B": make_track(id="B")}
    refs = [
        make_track_ref(id="A", cue_in=None, cue_out=None),
        make_track_ref(id="B", cue_in=None, cue_out=150.0, fade_out_bars=4),
    ]
    junctions = [make_junction(from_track="A", to_track="B", cue_out=120.0, cue_in=10.0)]

    # span[0] = 120 - 0 ; closer span = 150 - 10 ; no overlap (tier 3).
    assert estimated_duration_s(refs, junctions, tracks_by_id) == pytest.approx(260.0)


def test_two_track_plan_subtracts_a_blended_overlap(make_track, make_track_ref, make_junction):
    tracks_by_id = {"A": make_track(id="A"), "B": make_track(id="B")}
    refs = [
        make_track_ref(id="A", cue_in=None, cue_out=None),
        make_track_ref(id="B", cue_in=None, cue_out=150.0, fade_out_bars=4),
    ]
    junctions = [
        make_junction(
            from_track="A",
            to_track="B",
            cue_out=120.0,
            cue_in=10.0,
            length_bars=16,
            bar_seconds=2.0,
        )
    ]
    assert estimated_duration_s(refs, junctions, tracks_by_id) == pytest.approx(228.0)


def test_three_track_plan_spans_minus_overlaps(make_track, make_track_ref, make_junction):
    tracks_by_id = {x: make_track(id=x) for x in ("A", "B", "C")}
    refs = [
        make_track_ref(id="A", cue_in=None, cue_out=None),
        make_track_ref(id="B", cue_in=None, cue_out=None),
        make_track_ref(id="C", cue_in=None, cue_out=200.0, fade_out_bars=4),
    ]
    junctions = [
        make_junction(from_track="A", to_track="B", cue_out=100.0, cue_in=8.0),
        make_junction(from_track="B", to_track="C", cue_out=180.0, cue_in=12.0),
    ]
    # 100 + (180 - 8) + (200 - 12) = 460 ; no overlaps.
    assert estimated_duration_s(refs, junctions, tracks_by_id) == pytest.approx(460.0)


def test_closer_with_no_cue_out_falls_back_to_track_duration(
    make_track, make_track_ref, make_junction
):
    tracks_by_id = {"A": make_track(id="A"), "B": make_track(id="B", duration=195.0)}
    refs = [
        make_track_ref(id="A", cue_in=None, cue_out=None),
        make_track_ref(id="B", cue_in=None, cue_out=None),
    ]
    junctions = [make_junction(from_track="A", to_track="B", cue_out=120.0, cue_in=10.0)]
    # closer span = 195 (Track.duration) - 10 = 185 ; + 120 = 305.
    assert estimated_duration_s(refs, junctions, tracks_by_id) == pytest.approx(305.0)
