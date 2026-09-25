"""Camelot-wheel-adjacency track ordering — a deliberately hard-gated
experiment. `resources/ai-dj-domain-and-architecture.md` §1.1 is explicit
that key is normally treated as a soft score, "never a hard gate... a strict
gate can leave the search with no legal successor and dead-end" — this
module does exactly that on purpose, to test the consequence directly rather
than around it. Real key estimates on this repertoire are independently
flagged (same doc) as "confident but meaningless" — a musically-nonsensical
chain that nonetheless satisfies every Camelot rule syntactically is an
expected possible outcome of this experiment, not a bug.
"""

from ingestion.orchestrator.schema import Track
from processing.edge_builder.camelot import key_distance, reachable_keys


def order_by_camelot(tracks: list[Track], seed_track: str | None = None) -> list[str]:
    """Backtracking DFS over the Camelot-adjacency graph — guarantees finding
    a full free-move-only chain through every eligible track when one
    exists, unlike greedy nearest-neighbor, which can dead-end even when a
    full ordering exists elsewhere in the search space (at N~15 tracks with
    branching factor <= 3, full DFS is trivially fast).

    Tracks with an unparseable/missing key (`reachable_keys` returns an
    empty set) can never appear in a Camelot-only chain and are dropped from
    the candidate pool entirely, not treated as isolated single-node chains.

    Falls back to the longest partial chain found across every attempted
    start if no full ordering exists — this *is* the "stop early" behavior,
    not a second algorithm. Deliberately no "relax to nearest key" fallback
    when stuck: that would quietly reintroduce the soft-score-vs-hard-gate
    tension this module exists to test the absence of.
    """
    by_id = {t.id: t for t in tracks}
    ids = [t.id for t in tracks if reachable_keys(t.key)]
    adjacency = {
        a: {b for b in ids if b != a and by_id[b].key in reachable_keys(by_id[a].key)} for a in ids
    }

    best_path: list[str] = []

    def dfs(path: list[str], used: set[str]) -> bool:
        nonlocal best_path
        if len(path) > len(best_path):
            best_path = path[:]
        if len(path) == len(ids):
            return True
        candidates = sorted(
            adjacency[path[-1]] - used,
            key=lambda c: (
                key_distance(by_id[path[-1]].key, by_id[c].key),
                abs(by_id[path[-1]].bpm - by_id[c].bpm),
            ),
        )
        for candidate in candidates:
            path.append(candidate)
            used.add(candidate)
            if dfs(path, used):
                return True
            path.pop()
            used.remove(candidate)
        return False

    starts = [seed_track] if seed_track is not None else ids
    for start in starts:
        if start not in ids:
            continue
        if dfs([start], {start}):
            return best_path

    return best_path
