from collections.abc import Sequence

import numpy as np

from ingestion.orchestrator.schema import Track
from processing.path_search.config import PathSearchConfig

_VALID_ARCS = ("arc", "rise", "flat")


def track_energy(track: Track) -> float:
    """Short-term LUFS per bar, reduced to one number per track (D23).

    Median, not mean: an ``energy_curve`` includes near-silent intro/outro bars
    where short-term LUFS can hit -70, and the mean would let those drag the
    whole-track figure down.
    """
    return float(np.median(np.asarray(track.energy_curve, dtype=float)))


def pool_energy_percentiles(pool: Sequence[Track]) -> tuple[float, float]:
    """The pool's 5th and 95th percentile of ``track_energy``.

    Percentiles, not min-max: one quiet track would otherwise compress every other
    track's normalised energy into a narrow band, flattening the arc signal into
    noise. This reuses the convention edge_builder's ``normalized_vocal_mask``
    already follows against a 95th percentile (D22) — plain ``numpy.percentile``,
    default linear interpolation.
    """
    energies = np.array([track_energy(t) for t in pool], dtype=float)
    return float(np.percentile(energies, 5)), float(np.percentile(energies, 95))


def energy_norm(track_energy_value: float, p05: float, p95: float) -> float:
    """``clamp((e - p05) / (p95 - p05), 0, 1)``. Degenerate pool (``p95 <= p05``)
    scores a neutral ``0.5``."""
    spread = p95 - p05
    if spread <= 0:
        return 0.5
    return float(np.clip((track_energy_value - p05) / spread, 0.0, 1.0))


def energy_norm_array(pool: Sequence[Track]) -> np.ndarray:
    """Pool-aligned ``energy_norm`` for every track, using the pool's own p05/p95
    (spec §11 step 2). Returns all ``0.5`` on a degenerate pool."""
    p05, p95 = pool_energy_percentiles(pool)
    if p95 - p05 <= 0:
        return np.full(len(pool), 0.5)
    energies = np.array([track_energy(t) for t in pool], dtype=float)
    return np.clip((energies - p05) / (p95 - p05), 0.0, 1.0)


def target(p: float, config: PathSearchConfig) -> float:
    """Target normalised energy at normalised position ``p`` in ``[0, 1]``.

    - ``"arc"`` — piecewise-linear through three points: ``arc_start_level`` at
      ``p = 0``, ``1.0`` at ``p = arc_peak_position``, ``arc_end_level`` at
      ``p = 1`` (spec §1.10's "builds, peaks, comes down").
    - ``"rise"`` — ``target(p) = p`` (monotonic build).
    - ``"flat"`` — ``target(p) = arc_start_level`` (control shape).
    """
    if config.energy_arc == "arc":
        return float(
            np.interp(
                p,
                [0.0, config.arc_peak_position, 1.0],
                [config.arc_start_level, 1.0, config.arc_end_level],
            )
        )
    if config.energy_arc == "rise":
        return float(p)
    if config.energy_arc == "flat":
        return float(config.arc_start_level)
    raise ValueError(f"unknown energy_arc: {config.energy_arc!r}; expected one of {_VALID_ARCS}")


def target_curve(k_eff: int, config: PathSearchConfig) -> np.ndarray:
    """``target(i / (k_eff - 1))`` for ``i`` in ``0..k_eff-1``. Requires
    ``k_eff >= 2`` (guarded upstream by the ``NoViablePathError`` check)."""
    positions = np.arange(k_eff, dtype=float) / (k_eff - 1)
    if config.energy_arc == "arc":
        return np.interp(
            positions,
            [0.0, config.arc_peak_position, 1.0],
            [config.arc_start_level, 1.0, config.arc_end_level],
        )
    if config.energy_arc == "rise":
        return positions
    if config.energy_arc == "flat":
        return np.full(k_eff, float(config.arc_start_level))
    raise ValueError(f"unknown energy_arc: {config.energy_arc!r}; expected one of {_VALID_ARCS}")


def arc_deviation(
    path_energy_norms: Sequence[float],
    k_eff: int,
    config: PathSearchConfig,
) -> float:
    """``mean_i | energy_norm(path[i]) - target(i / (k_eff - 1)) |`` (spec §5).

    The position denominator is ``k_eff - 1`` — the FINAL count — never ``n - 1``,
    so the arc steers the beam from the very first extension rather than only once
    a path is complete. This is safe because the beam only ever compares paths of
    equal length (spec §9), so the length-dependent denominator is uniform across
    every comparison it takes part in. Both operands are in ``[0, 1]``, so the
    result is too — no clamp needed.
    """
    norms = np.asarray(path_energy_norms, dtype=float)
    targets = target_curve(k_eff, config)[: len(norms)]
    return float(np.mean(np.abs(norms - targets)))
