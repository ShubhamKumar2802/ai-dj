import itertools

from processing.path_search.beam import (
    beam_step,
    build_track_arrays,
    extend_path,
    rank_finished,
    rescore,
    run_beam,
    seed_beam,
)
from processing.path_search.config import PathSearchConfig
from processing.path_search.pool import compute_k_eff


def _pool(make_track, ids, **track_kwargs):
    return [make_track(id=x, **track_kwargs) for x in ids]


def _brute_force_min_ordering(ids, edges):
    """Cheapest Sigma edge_costs over every ordering that visits all ids, tie-broken
    on the id tuple — the exhaustive answer a hand-enumerable pool must match."""
    best = None
    for order in itertools.permutations(ids):
        pairs = list(zip(order, order[1:]))
        if any((a, b) not in edges.edges for a, b in pairs):
            continue
        cost = sum(edges.edges[(a, b)].cost for a, b in pairs)
        candidate = (cost, order)
        if best is None or candidate < best:
            best = candidate
    return best[1] if best else None


def test_every_beam_generation_has_uniform_length(make_track, fully_connected):
    ids = list("abcdef")
    pool = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)
    config = PathSearchConfig(beam_width=4, target_track_count=5)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    beam = seed_beam(pool, arrays, config)
    first = [ext for s in beam for ext in extend_path(s, edges, arrays, config.min_play_seconds)]
    for path in first:
        rescore(path, arrays, k_eff, config)
    first.sort(key=lambda p: (p.total_cost, p.track_ids))
    beam = first[: config.beam_width]

    completed = []
    while beam and len(beam[0].track_ids) < k_eff:
        assert len({len(p.track_ids) for p in beam}) == 1  # THE invariant
        beam, newly = beam_step(beam, edges, arrays, k_eff, config)
        completed.extend(newly)

    assert not beam or {len(p.track_ids) for p in beam} == {k_eff}
    assert all(len(p.track_ids) < k_eff for p in completed)
    assert len(beam) <= config.beam_width


def test_a_pool_where_most_paths_dead_end_still_returns_the_one_long_path(
    make_track, make_scored_edges
):
    ids = list("abcde")
    pool = _pool(make_track, ids)
    # A single chain a->b->c->d->e. Every seed but `a` dead-ends short.
    edges = make_scored_edges({(x, y): {"cost": 1.0} for x, y in zip(ids, ids[1:])})
    config = PathSearchConfig(target_track_count=5)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    finished, terminated_on = run_beam(pool, edges, arrays, k_eff, config)

    ranked = rank_finished(finished)
    assert ranked[0].track_ids == ("a", "b", "c", "d", "e")
    assert terminated_on == "k_reached"
    # The shorter dead-ends survived in `finished` but rank below the full path.
    assert any(len(p.track_ids) < 5 for p in finished)


def test_hand_enumerable_pool_finds_the_brute_force_optimum(make_track, make_scored_edges):
    ids = list("abcd")
    pool = _pool(make_track, ids)
    # Chain a->b->c->d costs 1 per hop; every other ordered pair costs 5. All
    # tracks are identical, so path-level terms are constant across orderings and
    # only Sigma edge_costs decides.
    spec = {}
    for a in ids:
        for b in ids:
            if a != b:
                spec[(a, b)] = {"cost": 1.0 if (a, b) in list(zip(ids, ids[1:])) else 5.0}
    edges = make_scored_edges(spec)
    config = PathSearchConfig(beam_width=50, target_track_count=4)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    finished, _ = run_beam(pool, edges, arrays, k_eff, config)
    winner = rank_finished(finished)[0]

    assert winner.track_ids == _brute_force_min_ordering(ids, edges)
    assert winner.track_ids == ("a", "b", "c", "d")


def test_identical_cost_ties_are_broken_deterministically(make_track, fully_connected):
    ids = list("abcd")
    config = PathSearchConfig(beam_width=50, target_track_count=4)

    def _winner(track_ids, edge_ids):
        pool = _pool(make_track, track_ids)
        edges = fully_connected(edge_ids, cost=1.0)
        arrays = build_track_arrays(pool)
        k_eff = compute_k_eff(config.target_track_count, len(pool))
        finished, _ = run_beam(pool, edges, arrays, k_eff, config)
        return rank_finished(finished)[0].track_ids

    # Every full ordering ties on total_cost; the lexicographically smallest tuple
    # must win, regardless of pool / edge insertion order.
    assert _winner(ids, ids) == ("a", "b", "c", "d")
    assert _winner(list(reversed(ids)), list(reversed(ids))) == ("a", "b", "c", "d")
    assert _winner(ids, ids) == _winner(list(reversed(ids)), ids)


def test_a_missing_edge_key_is_no_edge_not_zero(make_track, fully_connected, make_scored_edges):
    ids = list("abcd")
    pool = _pool(make_track, ids)
    full = fully_connected(ids, cost=1.0)
    # Drop b->c entirely. If it were treated as cost 0, an a,b,c,d ordering would
    # be the cheapest path; instead that ordering is simply unreachable.
    edges = make_scored_edges(edge for key, edge in full.edges.items() if key != ("b", "c"))
    assert ("b", "c") not in edges.edges
    config = PathSearchConfig(beam_width=50, target_track_count=4)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    finished, _ = run_beam(pool, edges, arrays, k_eff, config)
    for path in finished:
        consecutive = list(zip(path.track_ids, path.track_ids[1:]))
        assert ("b", "c") not in consecutive


def test_no_track_is_ever_repeated(make_track, fully_connected):
    ids = list("abcdef")
    pool = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)
    config = PathSearchConfig(beam_width=10, target_track_count=6)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    finished, _ = run_beam(pool, edges, arrays, k_eff, config)
    for path in finished:
        assert len(set(path.track_ids)) == len(path.track_ids)


def test_out_of_order_interior_cues_reject_the_extension(make_track, make_scored_edges):
    ids = list("abc")
    pool = _pool(make_track, ids)
    config = PathSearchConfig(target_track_count=3, min_play_seconds=8.0)
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    # Edge a->b hands B a LATE cue-in (180); edge b->c hands B an EARLY cue-out
    # (60). B's play span would be -120 s.
    bad = make_scored_edges(
        {("a", "b"): {"cost": 0.1, "cue_in": 180.0}, ("b", "c"): {"cost": 0.1, "cue_out": 60.0}}
    )
    finished, terminated_on = run_beam(pool, bad, arrays, k_eff, config)
    assert all(p.track_ids != ("a", "b", "c") for p in finished)
    assert terminated_on == "pool_exhausted"

    # Sanity: an in-order cue-in makes the very same chain feasible.
    good = make_scored_edges(
        {("a", "b"): {"cost": 0.1, "cue_in": 10.0}, ("b", "c"): {"cost": 0.1, "cue_out": 60.0}}
    )
    finished, terminated_on = run_beam(pool, good, arrays, k_eff, config)
    assert any(p.track_ids == ("a", "b", "c") for p in finished)
    assert terminated_on == "k_reached"


def test_seed_track_pins_position_zero(make_track, fully_connected):
    ids = list("abcd")
    pool = _pool(make_track, ids)
    edges = fully_connected(ids, cost=1.0)
    config = PathSearchConfig(beam_width=50, target_track_count=4, seed_track="c")
    arrays = build_track_arrays(pool)
    k_eff = compute_k_eff(config.target_track_count, len(pool))

    seeds = seed_beam(pool, arrays, config)
    assert [s.track_ids for s in seeds] == [("c",)]

    finished, _ = run_beam(pool, edges, arrays, k_eff, config)
    assert all(p.track_ids[0] == "c" for p in finished)
