from ingestion.orchestrator.schema import Track
from processing.edge_builder.schema import ScoredEdges


def tracks_in_any_edge(edges: ScoredEdges) -> set[str]:
    """Every track id that appears as the `from` or `to` side of at least one edge."""
    present: set[str] = set()
    for from_track, to_track in edges.edges:
        present.add(from_track)
        present.add(to_track)
    return present


def filter_pool(tracks: list[Track], edges: ScoredEdges) -> list[Track]:
    """The node pool for the search — spec §3's four drops, input order preserved.

    - ``status == "excluded"`` — D7 quarantine; D10's one hard musical constraint.
    - ``len(downbeat_times) < 2`` — no bars, therefore no energy curve.
    - ``bpm <= 0`` — the tempo estimate failed outright (same guard edge_builder applies).
    - absent from every edge — unreachable and unleavable.

    ``cut_only`` tracks stay: D7 only restricts which tiers they may use, and
    edge_builder already priced that restriction into every edge they appear on.
    Dropping them here would punish the same quarantine twice.
    """
    reachable = tracks_in_any_edge(edges)
    return [
        track
        for track in tracks
        if track.status != "excluded"
        and len(track.downbeat_times) >= 2
        and track.bpm > 0
        and track.id in reachable
    ]


def compute_k_eff(target_track_count: int, pool_size: int) -> int:
    """``min(target_track_count, pool_size)`` — spec §5.

    Not the raw target: scoring every candidate set against an arc shape it cannot
    physically reach (a 12-track pool asked for 15) makes the arc's comedown
    structurally unreachable. Callers raise ``NoViablePathError`` when this is < 2,
    which also guards the ``K_eff - 1`` divisions in §5/§6.
    """
    return min(target_track_count, pool_size)
