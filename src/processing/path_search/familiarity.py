from collections.abc import Sequence

import numpy as np

from ingestion.orchestrator.schema import Track

_NEUTRAL = 0.5


def pool_familiarity_mean(pool: Sequence[Track]) -> float | None:
    """Mean of the non-null ``familiarity_score`` values in the pool, or ``None``
    when no track is scored."""
    known = [t.familiarity_score for t in pool if t.familiarity_score is not None]
    if not known:
        return None
    return float(np.mean(known))


def familiarity_of(track: Track, pool_mean: float | None) -> float:
    """The track's own score if set; else the pool mean of known scores if any are
    known; else a neutral ``0.5``.

    Never ``0.0`` for an unknown: that would look like the *best possible* value
    in a minimised objective, so the search would systematically favour precisely
    the tracks whose metadata is missing (edge_builder §4's confidence-blend
    reasoning).
    """
    if track.familiarity_score is not None:
        return float(track.familiarity_score)
    if pool_mean is not None:
        return pool_mean
    return _NEUTRAL


def familiarity_array(pool: Sequence[Track]) -> np.ndarray:
    """Pool-aligned ``familiarity_of`` with the fallback applied once (spec §11
    step 2). In v1 every entry is ``0.5`` — no track carries a score yet."""
    pool_mean = pool_familiarity_mean(pool)
    return np.array([familiarity_of(t, pool_mean) for t in pool], dtype=float)


def familiarity_deficit(path_familiarities: Sequence[float]) -> float:
    """``1 - mean(familiarity)`` (spec §7).

    Written as a deficit so D3's ``+ nu *`` sign stays literally correct in a
    minimised objective: higher familiarity lowers the total. Constant ``0.5``
    across every candidate path in v1, so the term is inert — it is specced now so
    that build step 8 becomes a data change, not a code change.
    """
    return 1.0 - float(np.mean(np.asarray(path_familiarities, dtype=float)))
