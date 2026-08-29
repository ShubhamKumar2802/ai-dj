from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from ingestion.orchestrator.schema import Track
from processing.edge_builder.schema import ScoredEdges
from processing.path_search.boundaries import closer_cost_array, opener_cost_array
from processing.path_search.config import PathSearchConfig
from processing.path_search.energy_arc import energy_norm_array
from processing.path_search.familiarity import familiarity_array
from processing.path_search.feasibility import extension_is_feasible
from processing.path_search.objective import score_path
from processing.path_search.schema import ObjectiveTerms

_EMPTY_TERMS = ObjectiveTerms(
    edges_total=float("inf"),
    arc_deviation=float("inf"),
    diversity_penalty=float("inf"),
    familiarity_deficit=float("inf"),
    boundary=float("inf"),
)


@dataclass
class TrackArrays:
    """Everything the beam's hot loop needs about the pool, precomputed once and
    indexed by pool position — no ``Track`` object is touched during the search."""

    ids: list[str]
    index_of: dict[str, int]
    energy_norm: np.ndarray
    bpm: np.ndarray
    keys: list[str | None]
    familiarity: np.ndarray
    opener_cost: np.ndarray
    closer_cost: np.ndarray


@dataclass
class BeamPath:
    # The track-id sequence — also the deterministic tie-break tail (D14).
    track_ids: tuple[str, ...]
    # Cached pool-array positions, so a rescore skips K dict lookups.
    indices: tuple[int, ...]
    # O(1) "no track repeats" test (D10).
    used: frozenset[str]
    # The ONLY incrementally-accumulated term: one float add per extension.
    edges_total: float
    # The frontier track's incoming cue_in — the sole extra state the O(1)
    # feasibility check needs. None on a length-1 path.
    last_cue_in: float | None
    # Overwritten by every full rescore; inf/placeholder until the first one.
    total_cost: float = float("inf")
    terms: ObjectiveTerms = field(default_factory=lambda: _EMPTY_TERMS)


def build_track_arrays(pool: list[Track]) -> TrackArrays:
    """Spec §11 step 2 — the pool's per-track feature vectors, computed once."""
    ids = [t.id for t in pool]
    return TrackArrays(
        ids=ids,
        index_of={track_id: i for i, track_id in enumerate(ids)},
        energy_norm=energy_norm_array(pool),
        bpm=np.array([t.bpm for t in pool], dtype=float),
        keys=[t.key for t in pool],
        familiarity=familiarity_array(pool),
        opener_cost=opener_cost_array(pool),
        closer_cost=closer_cost_array(pool),
    )


def seed_beam(pool: list[Track], arrays: TrackArrays, config: PathSearchConfig) -> list[BeamPath]:
    """One length-1 path per pool track — or exactly one when ``config.seed_track``
    pins position 0 (the caller has already checked it is in the pool)."""
    if config.seed_track is not None:
        seed_ids = [config.seed_track]
    else:
        seed_ids = list(arrays.ids)
    return [
        BeamPath(
            track_ids=(track_id,),
            indices=(arrays.index_of[track_id],),
            used=frozenset({track_id}),
            edges_total=0.0,
            last_cue_in=None,
        )
        for track_id in seed_ids
    ]


def extend_path(
    path: BeamPath,
    edges: ScoredEdges,
    arrays: TrackArrays,
    min_play_seconds: float,
) -> list[BeamPath]:
    """Every feasible one-track extension of ``path``.

    Iterates ``arrays.ids`` — the stable pool order — never the ``edges`` dict, so
    the result never depends on dict iteration order (D14). A pair with no key in
    ``edges.edges`` is "no viable junction exists" and is skipped, never treated
    as cost 0.
    """
    last = path.track_ids[-1]
    extensions: list[BeamPath] = []
    for next_id in arrays.ids:
        if next_id in path.used:
            continue
        edge = edges.edges.get((last, next_id))
        if edge is None:
            continue
        if not extension_is_feasible(path.last_cue_in, edge.plan.cue_out, min_play_seconds):
            continue
        extensions.append(
            BeamPath(
                track_ids=path.track_ids + (next_id,),
                indices=path.indices + (arrays.index_of[next_id],),
                used=path.used | {next_id},
                edges_total=path.edges_total + edge.cost,
                last_cue_in=edge.plan.cue_in,
            )
        )
    return extensions


def rescore(path: BeamPath, arrays: TrackArrays, k_eff: int, config: PathSearchConfig) -> None:
    """Recompute the full objective over ``path`` and write ``total_cost`` +
    ``terms`` in place (D3's "extend, rescore, prune")."""
    idx = list(path.indices)
    score, terms = score_path(
        path_energy_norms=arrays.energy_norm[idx],
        path_bpms=arrays.bpm[idx],
        path_keys=[arrays.keys[i] for i in idx],
        path_familiarities=arrays.familiarity[idx],
        opener_boundary_cost=float(arrays.opener_cost[path.indices[0]]),
        closer_boundary_cost=float(arrays.closer_cost[path.indices[-1]]),
        edges_total=path.edges_total,
        k_eff=k_eff,
        config=config,
    )
    path.total_cost = score
    path.terms = terms


def _sort_key(path: BeamPath) -> tuple[float, tuple[str, ...]]:
    return path.total_cost, path.track_ids


def beam_step(
    beam: list[BeamPath],
    edges: ScoredEdges,
    arrays: TrackArrays,
    k_eff: int,
    config: PathSearchConfig,
) -> tuple[list[BeamPath], list[BeamPath]]:
    """One extend / retire / rescore / prune round.

    Returns ``(kept_beam, newly_completed)``. A path that produces zero feasible
    extensions and already has length >= 2 is RETIRED into ``newly_completed`` —
    neither carried forward (which would put mixed-length paths in one beam and
    break the equal-length assumption §5/§6 rely on) nor discarded (which would
    throw away a legitimate shorter fallback). Its score is whatever its last
    rescore set, which was at its current — now final — length.
    """
    survivors: list[BeamPath] = []
    newly_completed: list[BeamPath] = []
    for path in beam:
        extensions = extend_path(path, edges, arrays, config.min_play_seconds)
        if extensions:
            survivors.extend(extensions)
        elif len(path.track_ids) >= 2:
            newly_completed.append(path)
    for path in survivors:
        rescore(path, arrays, k_eff, config)
    survivors.sort(key=_sort_key)
    return survivors[: config.beam_width], newly_completed


def run_beam(
    pool: list[Track],
    edges: ScoredEdges,
    arrays: TrackArrays,
    k_eff: int,
    config: PathSearchConfig,
) -> tuple[list[BeamPath], Literal["k_reached", "pool_exhausted"]]:
    """Seed, extend-once-unpruned, then loop ``beam_step`` until every survivor
    has length ``k_eff`` or the beam empties (spec §9).

    ``terminated_on`` is ``"k_reached"`` when a path actually reached ``k_eff``,
    else ``"pool_exhausted"`` — which means *this beam* exhausted, not that the
    pool provably did.
    """
    beam = seed_beam(pool, arrays, config)

    # Step 2: do NOT prune before the first edge exists. A length-1 path has no
    # edge cost, so pruning here would rank openers on path-level terms alone and
    # discard the best one on noise.
    first_generation: list[BeamPath] = []
    for seed in beam:
        first_generation.extend(extend_path(seed, edges, arrays, config.min_play_seconds))
    if not first_generation:
        return [], "pool_exhausted"
    for path in first_generation:
        rescore(path, arrays, k_eff, config)
    first_generation.sort(key=_sort_key)
    beam = first_generation[: config.beam_width]

    completed: list[BeamPath] = []
    while beam and len(beam[0].track_ids) < k_eff:
        beam, newly_completed = beam_step(beam, edges, arrays, k_eff, config)
        completed.extend(newly_completed)

    finished = completed + beam
    reached_k = bool(beam) and len(beam[0].track_ids) == k_eff
    return finished, "k_reached" if reached_k else "pool_exhausted"


def rank_finished(finished: list[BeamPath]) -> list[BeamPath]:
    """Spec §9 step 4 — the longest achieved length wins outright; within that
    cohort, ascending ``(total_cost, track_ids)``. Never pad a short set to K."""
    if not finished:
        return []
    max_len = max(len(path.track_ids) for path in finished)
    cohort = [path for path in finished if len(path.track_ids) == max_len]
    return sorted(cohort, key=_sort_key)


def pick_winner(finished: list[BeamPath]) -> BeamPath:
    return rank_finished(finished)[0]


def select_alternatives(finished: list[BeamPath], n: int) -> list[BeamPath]:
    """The next-best complete paths behind the winner. These are beam neighbours
    and share long prefixes with the winner (spec Q12)."""
    if n <= 0:
        return []
    return rank_finished(finished)[1 : 1 + n]
