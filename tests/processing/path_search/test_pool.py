from processing.path_search.pool import compute_k_eff, filter_pool, tracks_in_any_edge


def _edges_over(make_scored_edges, ids):
    return make_scored_edges({(a, b): {} for a in ids for b in ids if a != b})


def test_tracks_in_any_edge_collects_both_sides(make_scored_edges):
    edges = make_scored_edges({("a", "b"): {}, ("b", "c"): {}})
    assert tracks_in_any_edge(edges) == {"a", "b", "c"}


def test_excluded_dropped(make_track, make_scored_edges):
    tracks = [
        make_track(id="a"),
        make_track(id="b", status="excluded"),
        make_track(id="c"),
    ]
    edges = _edges_over(make_scored_edges, ["a", "b", "c"])
    assert [t.id for t in filter_pool(tracks, edges)] == ["a", "c"]


def test_cut_only_kept(make_track, make_scored_edges):
    tracks = [make_track(id="a"), make_track(id="b", status="cut_only")]
    edges = _edges_over(make_scored_edges, ["a", "b"])
    assert [t.id for t in filter_pool(tracks, edges)] == ["a", "b"]


def test_bar_less_and_non_positive_bpm_dropped(make_track, make_scored_edges):
    tracks = [
        make_track(id="a"),
        make_track(id="b", downbeat_times=[0.0]),
        make_track(id="c", bpm=0.0),
        make_track(id="d", bpm=-1.0),
    ]
    edges = _edges_over(make_scored_edges, ["a", "b", "c", "d"])
    assert [t.id for t in filter_pool(tracks, edges)] == ["a"]


def test_absent_from_every_edge_dropped(make_track, make_scored_edges):
    tracks = [make_track(id="a"), make_track(id="b"), make_track(id="orphan")]
    edges = make_scored_edges({("a", "b"): {}, ("b", "a"): {}})
    assert [t.id for t in filter_pool(tracks, edges)] == ["a", "b"]


def test_input_order_preserved(make_track, make_scored_edges):
    tracks = [make_track(id=x) for x in ("z", "m", "a")]
    edges = _edges_over(make_scored_edges, ["z", "m", "a"])
    assert [t.id for t in filter_pool(tracks, edges)] == ["z", "m", "a"]


def test_compute_k_eff_clamps_to_pool_size():
    assert compute_k_eff(15, 12) == 12
    assert compute_k_eff(15, 20) == 15
    assert compute_k_eff(2, 2) == 2
