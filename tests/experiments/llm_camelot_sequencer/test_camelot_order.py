from experiments.llm_camelot_sequencer.camelot_order import order_by_camelot


def test_finds_a_full_chain_when_one_exists(make_track):
    # A linear Camelot chain: 1A -> 2A -> 3A -> 4A, each only adjacent to its
    # immediate neighbor (no cross-links — wheel_distance >= 2 otherwise).
    tracks = [
        make_track(id="t1a", key="1A", bpm=100.0),
        make_track(id="t2a", key="2A", bpm=101.0),
        make_track(id="t3a", key="3A", bpm=102.0),
        make_track(id="t4a", key="4A", bpm=103.0),
    ]

    order = order_by_camelot(tracks)

    assert order == ["t1a", "t2a", "t3a", "t4a"]


def test_returns_longest_partial_chain_when_no_full_ordering_exists(make_track):
    # Three tracks with mutually unreachable keys (wheel_distance >= 2 apart,
    # different letters) — no edges at all in the adjacency graph.
    tracks = [
        make_track(id="t1a", key="1A"),
        make_track(id="t6a", key="6A"),
        make_track(id="t11a", key="11A"),
    ]

    order = order_by_camelot(tracks)

    assert len(order) == 1  # no two tracks are adjacent — best is a single track
    assert order[0] in {"t1a", "t6a", "t11a"}


def test_tracks_with_unparseable_key_are_excluded_from_the_pool(make_track):
    tracks = [
        make_track(id="t1a", key="1A", bpm=100.0),
        make_track(id="t2a", key="2A", bpm=101.0),
        make_track(id="t-nokey", key=None),
    ]

    order = order_by_camelot(tracks)

    assert "t-nokey" not in order
    assert order == ["t1a", "t2a"]


def test_seed_track_pins_the_start_even_if_a_longer_chain_starts_elsewhere(make_track):
    # Same 1A-2A-3A-4A chain as above, but forced to start from the middle
    # (2A) — bpm values force a deterministic branch choice (3A is closer in
    # bpm to 2A than 1A is, so the DFS explores 2A->3A->4A before 2A->1A).
    tracks = [
        make_track(id="t1a", key="1A", bpm=100.0),
        make_track(id="t2a", key="2A", bpm=120.0),
        make_track(id="t3a", key="3A", bpm=121.0),
        make_track(id="t4a", key="4A", bpm=140.0),
    ]

    order = order_by_camelot(tracks, seed_track="t2a")

    assert order[0] == "t2a"
    assert order == ["t2a", "t3a", "t4a"]  # can't reach t1a and stay at length 4


def test_seed_track_not_in_pool_yields_empty_order(make_track):
    tracks = [make_track(id="t1a", key="1A")]

    assert order_by_camelot(tracks, seed_track="not-a-real-id") == []


def test_single_track_pool_returns_that_track_alone(make_track):
    tracks = [make_track(id="only-one", key="8A")]

    assert order_by_camelot(tracks) == ["only-one"]


def test_empty_pool_returns_empty_order():
    assert order_by_camelot([]) == []
