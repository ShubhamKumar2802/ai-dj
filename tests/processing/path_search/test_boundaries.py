import pytest

from processing.path_search.boundaries import (
    boundary_cost,
    closer_cost,
    opener_cost,
    relax_closer,
)

# The plan-level half of D24 — interior TrackRefs keeping cue_in/cue_out at None,
# the opener getting cue_in=None — is asserted end-to-end in test_search.py, since
# it is plan_builder that assembles the TrackRefs.


def test_opener_cost_ordering_across_the_three_cases(make_track, make_cue):
    riser = make_track(cue_ins=[make_cue(kind="riser_start")])
    intro_end = make_track(cue_ins=[make_cue(kind="intro_end")])
    some_intro = make_track(cue_ins=[make_cue(kind="hook_in")], free_intro_end=8.0, grid_start=0.0)
    no_intro = make_track(cue_ins=[make_cue(kind="hook_in")], free_intro_end=0.0, grid_start=0.0)

    assert opener_cost(riser) == 0.0
    assert opener_cost(intro_end) == 0.0
    assert opener_cost(some_intro) == 0.5
    assert opener_cost(no_intro) == 1.0
    assert opener_cost(riser) < opener_cost(some_intro) < opener_cost(no_intro)


def test_closer_cost_is_constant_one_without_outro_start(make_track, make_cue):
    assert closer_cost(make_track(cue_outs=[make_cue(kind="chorus_end")])) == 1.0
    assert closer_cost(make_track(cue_outs=[make_cue(kind="outro_start")])) == 0.0


def test_boundary_cost_is_the_mean_of_the_two_halves(make_track, make_cue):
    opener = make_track(cue_ins=[make_cue(kind="riser_start")])  # 0.0
    closer = make_track(cue_outs=[make_cue(kind="chorus_end")])  # 1.0
    assert boundary_cost(opener, closer) == pytest.approx(0.5)


def test_relax_closer_with_outro_start_plays_to_natural_end(make_track, make_cue):
    track = make_track(cue_outs=[make_cue(position=150.0, kind="outro_start")])
    assert relax_closer(track, closer_fade_bars=4) == (None, None)


def test_relax_closer_without_outro_start_time_boxes_then_fades(make_track, make_cue):
    track = make_track(
        cue_outs=[make_cue(position=150.0, kind="chorus_end"), make_cue(position=170.0)]
    )
    assert relax_closer(track, closer_fade_bars=4) == (150.0, 4)


def test_relax_closer_with_no_cue_outs_runs_to_end_and_still_fades(make_track):
    track = make_track(cue_outs=[])
    assert relax_closer(track, closer_fade_bars=6) == (None, 6)
