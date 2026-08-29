import pytest

from processing.edge_builder.config import EdgeBuilderConfig
from processing.path_search.config import PathSearchConfig
from processing.path_search.objective import total
from processing.path_search.schema import NoViablePathError
from processing.path_search.search import search_path


def _pool(make_track, ids, **kwargs):
    # cue_outs without an outro_start cue -> the closer takes the fade fallback.
    kwargs.setdefault("cue_outs", None)
    return [
        make_track(
            id=x,
            bpm=120.0 + 3 * i,
            key=["8A", "9A", "10A", "11A", "12A", "1A"][i % 6],
            energy_curve=[float(-14 + i)] * 3,
            cue_outs=[],
            **{k: v for k, v in kwargs.items() if k != "cue_outs"},
        )
        for i, x in enumerate(ids)
    ]


def _pool_with_chorus_end_closers(make_track, make_cue, ids):
    return [
        make_track(
            id=x,
            bpm=120.0 + 3 * i,
            key=["8A", "9A", "10A", "11A", "12A", "1A"][i % 6],
            energy_curve=[float(-14 + i)] * 3,
            cue_outs=[make_cue(position=150.0, kind="chorus_end")],
        )
        for i, x in enumerate(ids)
    ]


def test_mix_plan_shape_invariants(make_track, fully_connected):
    ids = list("abcde")
    tracks = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)

    result = search_path(tracks, edges, PathSearchConfig(target_track_count=5))
    plan = result.plan

    assert len(plan.junctions) == len(plan.tracks) - 1
    assert len({t.id for t in plan.tracks}) == len(plan.tracks)
    for i, junction in enumerate(plan.junctions):
        assert junction.from_track == plan.tracks[i].id
        assert junction.to_track == plan.tracks[i + 1].id
        # Copied verbatim from ScoredEdge.plan — the same object, never rebuilt.
        key = (plan.tracks[i].id, plan.tracks[i + 1].id)
        assert junction is edges.edges[key].plan


def test_d24_touches_only_the_two_ends(make_track, make_cue, fully_connected):
    ids = list("abcde")
    tracks = _pool_with_chorus_end_closers(make_track, make_cue, ids)
    edges = fully_connected(ids, cost=1.0)

    plan = search_path(tracks, edges, PathSearchConfig(target_track_count=5)).plan

    opener = plan.tracks[0]
    assert opener.cue_in is None and opener.cue_out is None and opener.fade_out_bars is None

    for interior in plan.tracks[1:-1]:
        assert interior.cue_in is None
        assert interior.cue_out is None
        assert interior.fade_out_bars is None

    closer = plan.tracks[-1]
    assert closer.cue_in is None
    assert closer.cue_out == pytest.approx(150.0)  # first cue_outs entry
    assert closer.fade_out_bars == 4  # closer_fade_bars, since no outro_start cue


def test_diagnostics_are_populated(make_track, fully_connected):
    ids = list("abcde")
    tracks = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)

    result = search_path(tracks, edges, PathSearchConfig(target_track_count=5))
    diag = result.diagnostics

    assert diag.achieved_track_count == 5
    assert diag.terminated_on == "k_reached"
    assert diag.pool_size == 5
    assert diag.excluded_count == 0
    assert diag.cut_only_count == 0
    assert diag.tier_histogram == {3: 4}  # every default junction is tier 3
    assert diag.estimated_duration_s > 0
    assert diag.total_cost == pytest.approx(total(diag.objective, PathSearchConfig()))
    assert diag.runner_up_costs == sorted(diag.runner_up_costs)
    assert all(cost >= diag.total_cost for cost in diag.runner_up_costs)


def test_alternatives_empty_by_default_and_populated_on_request(make_track, fully_connected):
    ids = list("abcde")
    tracks = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)

    assert search_path(tracks, edges, PathSearchConfig(target_track_count=5)).alternatives == []

    with_alts = search_path(tracks, edges, PathSearchConfig(target_track_count=5, n_alternatives=3))
    assert len(with_alts.alternatives) == 3
    winner_ids = tuple(t.id for t in with_alts.plan.tracks)
    for alt in with_alts.alternatives:
        assert tuple(t.id for t in alt.tracks) != winner_ids


def test_k_eff_clamps_to_the_pool_end_to_end(make_track, fully_connected):
    ids = list("abcd")
    tracks = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)

    result = search_path(tracks, edges, PathSearchConfig(target_track_count=15))

    assert result.diagnostics.achieved_track_count <= 4
    assert len(result.plan.tracks) == result.diagnostics.achieved_track_count
    assert result.plan.config.track_count == 15  # K as REQUESTED, not achieved


def test_pool_exhausted_when_the_target_cannot_be_reached(make_track, make_scored_edges):
    ids = list("abcde")
    tracks = _pool(make_track, ids)
    # A single chain a->b->c->d->e; ask for one more track than exists.
    edges = make_scored_edges({(x, y): {"cost": 1.0} for x, y in zip(ids, ids[1:])})

    result = search_path(tracks, edges, PathSearchConfig(target_track_count=5))
    assert result.diagnostics.terminated_on == "k_reached"
    assert result.diagnostics.achieved_track_count == 5

    # Now shorten the chain so nothing reaches 5.
    short = make_scored_edges({(x, y): {"cost": 1.0} for x, y in zip("abc", "bc")})
    tracks3 = _pool(make_track, list("abc"))
    result = search_path(tracks3, short, PathSearchConfig(target_track_count=5))
    assert result.diagnostics.terminated_on == "k_reached"  # k_eff clamps to 3
    assert result.diagnostics.achieved_track_count == 3


def test_no_viable_path_errors(make_track, make_scored_edges, fully_connected):
    # Empty input.
    with pytest.raises(NoViablePathError):
        search_path([], make_scored_edges({}), PathSearchConfig())

    # One viable track (the other is quarantined).
    tracks = _pool(make_track, ["a", "b"])
    tracks[1] = make_track(id="b", status="excluded")
    edges = fully_connected(["a", "b"], cost=1.0)
    with pytest.raises(NoViablePathError):
        search_path(tracks, edges, PathSearchConfig())

    # Two viable tracks but no edge between them in either direction.
    two = _pool(make_track, ["a", "b"])
    no_link = make_scored_edges({("a", "b"): {}, ("b", "a"): {}})
    # sanity: with the link it succeeds
    search_path(two, no_link, PathSearchConfig(target_track_count=2))
    with pytest.raises(NoViablePathError):
        search_path(two, make_scored_edges([]), PathSearchConfig(target_track_count=2))


def test_hygiene_failures_raise_value_error(make_track, fully_connected):
    tracks = _pool(make_track, list("abc"))
    edges = fully_connected(list("abc"), cost=1.0)

    with pytest.raises(ValueError):
        search_path(tracks, edges, PathSearchConfig(beam_width=0))
    with pytest.raises(ValueError):
        search_path(tracks, edges, PathSearchConfig(target_track_count=1))
    with pytest.raises(ValueError):
        search_path(tracks, edges, PathSearchConfig(energy_arc="parabola"))
    with pytest.raises(ValueError):
        search_path(tracks, edges, PathSearchConfig(seed_track="nope"))


def test_edge_config_is_recorded_as_provenance_only(make_track, fully_connected):
    ids = list("abcd")
    tracks = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)
    edge_config = EdgeBuilderConfig(enabled_tiers=frozenset({3}))

    without = search_path(tracks, edges, PathSearchConfig(target_track_count=4))
    with_cfg = search_path(tracks, edges, PathSearchConfig(target_track_count=4), edge_config)

    assert without.plan.config.edge_builder is None
    assert with_cfg.plan.config.edge_builder["enabled_tiers"] == frozenset({3})
    # Provenance only — it must not change which path is chosen.
    assert [t.id for t in without.plan.tracks] == [t.id for t in with_cfg.plan.tracks]
