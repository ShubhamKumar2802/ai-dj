from collections.abc import Sequence

import numpy as np

from processing.path_search.config import PathSearchConfig


def bpm_spread_deficit(path_bpms: Sequence[float], target_std: float) -> float:
    """``1 - clamp(stdev(bpm) / target_std, 0, 1)`` (spec §6).

    A path shorter than two tracks scores ``1.0`` — stdev is undefined. Sample
    stdev (``ddof=1``): a path is a sample of the set, not the population.
    """
    if len(path_bpms) < 2:
        return 1.0
    std = float(np.std(np.asarray(path_bpms, dtype=float), ddof=1))
    return 1.0 - float(np.clip(std / target_std, 0.0, 1.0))


def distinct_key_count(path_keys: Sequence[str | None]) -> int:
    """Distinct non-null Camelot keys, plus one if any key is null.

    Every unknown collapses into a single bucket, because a missing key is
    *unknown*, not a distinct key — mirroring edge_builder's refusal to let a null
    key score as a perfect match.
    """
    distinct = {key for key in path_keys if key is not None}
    return len(distinct) + (1 if any(key is None for key in path_keys) else 0)


def key_variety_deficit(path_keys: Sequence[str | None], k_eff: int) -> float:
    """``1 - clamp((distinct_keys - 1) / (k_eff - 1), 0, 1)`` (spec §6).

    ``k_eff - 1`` is the denominator on partial paths too, for the same
    equal-length reason ``arc_deviation`` relies on.
    """
    return 1.0 - float(np.clip((distinct_key_count(path_keys) - 1) / (k_eff - 1), 0.0, 1.0))


def diversity_penalty(
    path_bpms: Sequence[float],
    path_keys: Sequence[str | None],
    k_eff: int,
    config: PathSearchConfig,
) -> float:
    """``mean(bpm_spread_deficit, key_variety_deficit)`` — spec §6.

    The counterweight to ``Sigma edge_costs``: the cheapest edges are always
    nearest neighbours, so a pure edge-sum converges on fifteen tracks at one
    tempo in one key. A length-1 path scores ``1.0`` (both halves do).
    """
    return 0.5 * (
        bpm_spread_deficit(path_bpms, config.diversity_bpm_target_std)
        + key_variety_deficit(path_keys, k_eff)
    )
