import numpy as np

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.schema import PhraseBoundary
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures

# Checkerboard kernel half-width — an 8-bar window on each side of a
# candidate boundary. Implementer-chosen (spec §4 names the technique, not
# this value), matched to hook_min_bars' own ~8-bar plateau scale and F8's
# ~12-bar film phrasing.
_KERNEL_RADIUS_BARS = 4

_SCALAR_FIELDS = (
    "rms",
    "spectral_centroid",
    "spectral_flux",
    "low_band_energy",
    "high_band_energy",
)


def _feature_matrix(per_bar_features: list[PerBarFeatures]) -> np.ndarray:
    """(n_bars, 17) matrix: 5 scalar fields, each z-score normalized across
    the track (spectral_centroid's raw Hz scale — hundreds to thousands —
    would otherwise swamp rms/chroma's roughly-unit scale in any distance
    metric), concatenated with the 12-dim chroma_vector left as-is (already
    comparable across its own dimensions)."""
    n_bars = len(per_bar_features)
    if n_bars == 0:
        return np.zeros((0, len(_SCALAR_FIELDS) + 12))

    scalars = np.array(
        [[getattr(bar, field) for field in _SCALAR_FIELDS] for bar in per_bar_features],
        dtype=np.float64,
    )
    mean = scalars.mean(axis=0)
    std = scalars.std(axis=0)
    normalized = np.where(std > 0, (scalars - mean) / np.where(std > 0, std, 1.0), 0.0)

    chroma = np.array([bar.chroma_vector for bar in per_bar_features], dtype=np.float64)

    return np.concatenate([normalized, chroma], axis=1)


def _checkerboard_kernel(radius: int) -> np.ndarray:
    """2R x 2R block kernel: +1 in same-segment quadrants (top-left,
    bottom-right), -1 in cross-segment quadrants (top-right, bottom-left) —
    the standard Foote kernel."""
    same = np.ones((radius, radius))
    return np.block([[same, -same], [-same, same]])


def _local_similarity(features: np.ndarray, center: int, radius: int) -> np.ndarray:
    """Cosine similarity submatrix over features[center-radius:center+radius]
    only — never the full N x N matrix (spec §4's explicit distinction from
    v2's SSM step, a different question: "which sections repeat" vs. "where
    does a section end")."""
    window = features[center - radius : center + radius]
    norms = np.linalg.norm(window, axis=1, keepdims=True)
    unit = window / np.where(norms > 0, norms, 1.0)
    return unit @ unit.T


def _novelty_curve(features: np.ndarray, radius: int) -> np.ndarray:
    """novelty[i] = sum(kernel * local_similarity(features, i, radius)) for
    every bar with a full window on both sides; the first/last `radius` bars
    get novelty 0.0 — no full local window exists there."""
    n_bars = features.shape[0]
    kernel = _checkerboard_kernel(radius)
    novelty = np.zeros(n_bars)
    for i in range(radius, n_bars - radius):
        novelty[i] = float(np.sum(kernel * _local_similarity(features, i, radius)))
    return novelty


def _pick_peaks(novelty: np.ndarray, threshold: float) -> list[int]:
    """Indices of local maxima (strictly greater than both neighbors) at or
    above threshold."""
    return [
        i
        for i in range(1, len(novelty) - 1)
        if novelty[i] >= threshold and novelty[i] > novelty[i - 1] and novelty[i] > novelty[i + 1]
    ]


def detect_phrase_boundaries(
    raw: RawFeatures, config: CueDerivationConfig
) -> tuple[list[PhraseBoundary], float | None]:
    """Returns (phrase_grid, phrase_length_bars) — spec §4 (amended §9 step 2
    signature).

    D8: detect boundaries locally, never project a grid. A Foote checkerboard
    novelty curve over a local self-similarity window (never the full N x N
    SSM) picks up bar-to-bar discontinuities in the six per-bar feature
    fields. phrase_length_bars is advisory only (D8) — a summary statistic
    over detected gaps, never used downstream to predict the next boundary.
    """
    n_bars = len(raw.per_bar_features)
    if n_bars < 2 * _KERNEL_RADIUS_BARS + 1:
        return [], None

    features = _feature_matrix(raw.per_bar_features)
    novelty = _novelty_curve(features, _KERNEL_RADIUS_BARS)

    valid = novelty[_KERNEL_RADIUS_BARS : n_bars - _KERNEL_RADIUS_BARS]
    threshold = valid.mean() + config.phrase_boundary_novelty_std_multiplier * valid.std()
    peak_indices = _pick_peaks(novelty, threshold)

    phrase_grid: list[PhraseBoundary] = []
    previous_index: int | None = None
    for index in peak_indices:
        bars_since_previous = float(index - previous_index) if previous_index is not None else None
        phrase_grid.append(
            PhraseBoundary(
                position=raw.per_bar_features[index].start_time,
                strength=float(novelty[index]),
                bars_since_previous=bars_since_previous,
            )
        )
        previous_index = index

    phrase_length_bars = None
    if len(phrase_grid) >= 2:
        gaps = [b.bars_since_previous for b in phrase_grid[1:]]
        phrase_length_bars = float(np.median(gaps))

    return phrase_grid, phrase_length_bars
