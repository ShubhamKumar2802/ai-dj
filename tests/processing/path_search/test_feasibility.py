import pytest

from processing.path_search.feasibility import (
    extension_is_feasible,
    path_is_feasible,
    segment_span,
)


def test_segment_span():
    assert segment_span(10.0, 40.0) == pytest.approx(30.0)


def test_length_one_frontier_is_always_feasible():
    # prev_cue_in is None => the frontier track is not yet interior.
    assert extension_is_feasible(None, 5.0, 8.0) is True


def test_out_of_order_cues_rejected():
    # edge A->B picked a LATE cue-in for B (180.0); edge B->C picked an EARLY
    # cue-out for B (60.0). Span is -120.0 — a negative play duration.
    assert extension_is_feasible(180.0, 60.0, 8.0) is False


def test_span_just_below_floor_rejected():
    assert extension_is_feasible(100.0, 107.0, 8.0) is False


def test_span_exactly_at_floor_accepted():
    assert extension_is_feasible(100.0, 108.0, 8.0) is True


def test_path_is_feasible_full_scan(make_junction):
    # 3-track path A,B,C: junctions (A,B) then (B,C). B is the one interior track.
    ab = make_junction(from_track="A", to_track="B", cue_in=10.0)
    bc = make_junction(from_track="B", to_track="C", cue_out=200.0)
    assert path_is_feasible([ab, bc], 8.0) is True

    bc_early = make_junction(from_track="B", to_track="C", cue_out=15.0)
    assert path_is_feasible([ab, bc_early], 8.0) is False


def test_path_is_feasible_two_track_path_has_no_interior(make_junction):
    ab = make_junction(from_track="A", to_track="B")
    assert path_is_feasible([ab], 8.0) is True
