from common.contracts.schema import Junction
from ingestion.orchestrator.schema import Track
from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.schema import ScoredEdges
from processing.path_search.beam import build_track_arrays, rank_finished, run_beam
from processing.path_search.config import PathSearchConfig
from processing.path_search.duration import estimated_duration_s
from processing.path_search.plan_builder import build_mix_plan
from processing.path_search.pool import compute_k_eff, filter_pool
from processing.path_search.schema import (
    NoViablePathError,
    PathSearchResult,
    SearchDiagnostics,
)

_VALID_ARCS = ("arc", "rise", "flat")


def _tier_histogram(junctions: list[Junction]) -> dict[int, int]:
    histogram: dict[int, int] = {}
    for junction in junctions:
        histogram[junction.strategy_tier] = histogram.get(junction.strategy_tier, 0) + 1
    return histogram


def search_path(
    tracks: list[Track],
    edges: ScoredEdges,
    config: PathSearchConfig,
    edge_config: EdgeBuilderConfig | None = None,
) -> PathSearchResult:
    """Choose which K tracks, in what order — spec §11.

    A pure function of ``(Track[], ScoredEdges)``: it never touches audio, never
    re-derives a cue, never re-scores a junction, never re-picks a tier. It runs
    a beam search over the five-term objective and strings the pre-stored winning
    ``Junction``s together into a ``MixPlan``.

    ``edge_config`` is provenance only — it is recorded into
    ``MixPlanConfig.edge_builder`` and never influences the search.

    Raises ``ValueError`` for a caller bug (a one-track mix, an empty beam, an
    unknown arc, a ``seed_track`` outside the pool) and ``NoViablePathError`` when
    no two-track chain exists at all.
    """
    if config.beam_width < 1:
        raise ValueError(f"beam_width must be >= 1, got {config.beam_width}")
    if config.target_track_count < 2:
        raise ValueError(f"target_track_count must be >= 2, got {config.target_track_count}")
    if config.energy_arc not in _VALID_ARCS:
        raise ValueError(f"energy_arc must be one of {_VALID_ARCS}, got {config.energy_arc!r}")

    tracks_by_id = {track.id: track for track in tracks}

    pool = filter_pool(tracks, edges)
    k_eff = compute_k_eff(config.target_track_count, len(pool))
    if k_eff < 2:
        raise NoViablePathError(
            f"pool has {len(pool)} viable track(s) after filtering; need at least 2"
        )

    if config.seed_track is not None and config.seed_track not in {t.id for t in pool}:
        raise ValueError(f"seed_track {config.seed_track!r} is not in the viable pool")

    arrays = build_track_arrays(pool)
    finished, terminated_on = run_beam(pool, edges, arrays, k_eff, config)
    if not finished:
        raise NoViablePathError("no two-track chain exists in the edge set")

    ranked = rank_finished(finished)
    winner = ranked[0]

    plan = build_mix_plan(winner.track_ids, tracks_by_id, edges, config, edge_config)

    n_alternatives = max(0, min(config.n_alternatives, config.beam_width))
    alternatives = [
        build_mix_plan(path.track_ids, tracks_by_id, edges, config, edge_config)
        for path in ranked[1 : 1 + n_alternatives]
    ]

    diagnostics = SearchDiagnostics(
        total_cost=winner.total_cost,
        objective=winner.terms,
        achieved_track_count=len(winner.track_ids),
        estimated_duration_s=estimated_duration_s(plan.tracks, plan.junctions, tracks_by_id),
        tier_histogram=_tier_histogram(plan.junctions),
        pool_size=len(pool),
        excluded_count=sum(1 for track in tracks if track.status == "excluded"),
        cut_only_count=sum(1 for track in pool if track.status == "cut_only"),
        runner_up_costs=[path.total_cost for path in ranked[1:]],
        terminated_on=terminated_on,
    )
    return PathSearchResult(plan=plan, diagnostics=diagnostics, alternatives=alternatives)
