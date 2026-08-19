import numpy as np

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.schema import PhraseBoundary
from ingestion.feature_extractor.schema import RawFeatures


def _bar_index_at(raw: RawFeatures, position: float) -> int | None:
    """List index into per_bar_features/energy_curve/vocal_band_energy (all
    aligned 1:1, per feature_extractor spec §2) for the bar starting exactly
    at `position` — phrase_grid.py sets a PhraseBoundary's position to a
    bar's own start_time, so this is an exact float match, not a search."""
    for i, bar in enumerate(raw.per_bar_features):
        if bar.start_time == position:
            return i
    return None


def detect_hook(
    raw: RawFeatures,
    phrase_grid: list[PhraseBoundary],
    config: CueDerivationConfig,
) -> tuple[float | None, float | None]:
    """Returns (hook_in, hook_exit) — spec §6 (amended formula). Either or
    both may be None if no qualifying plateau/exit boundary is found;
    cues.py's preference order handles the fallback."""
    n_bars = len(raw.per_bar_features)
    if n_bars == 0:
        return None, None

    energy = np.asarray(raw.energy_curve, dtype=np.float64)
    vocal = np.asarray(raw.vocal_band_energy, dtype=np.float64)

    e_thr = np.percentile(energy, config.hook_high_energy_percentile * 100)
    v_thr = np.percentile(vocal, config.hook_high_vocal_percentile * 100)
    high = (energy >= e_thr) & (vocal >= v_thr)

    window = config.hook_min_bars
    plateau_start = None
    for i in range(n_bars - window + 1):
        if high[i : i + window].mean() >= config.hook_plateau_occupancy:
            plateau_start = i
            break

    if plateau_start is None:
        return None, None

    hook_in = raw.per_bar_features[plateau_start].start_time

    e_low, e_high = np.percentile(energy, [10, 90])
    v_low, v_high = np.percentile(vocal, [10, 90])
    energy_drop_threshold = config.hook_energy_drop_fraction * (e_high - e_low)
    vocal_drop_threshold = config.hook_vocal_drop_fraction * (v_high - v_low)

    plateau_end = plateau_start + window
    plateau_end_time = (
        raw.per_bar_features[plateau_end].start_time
        if plateau_end < n_bars
        else raw.per_bar_features[-1].end_time
    )

    hook_exit = None
    for boundary in phrase_grid:
        if boundary.position < plateau_end_time:
            continue
        bar_index = _bar_index_at(raw, boundary.position)
        if bar_index is None or bar_index == 0:
            continue
        energy_drop = energy[bar_index - 1] - energy[bar_index]
        vocal_drop = vocal[bar_index - 1] - vocal[bar_index]
        if energy_drop >= energy_drop_threshold and vocal_drop >= vocal_drop_threshold:
            hook_exit = boundary.position
            break

    return hook_in, hook_exit
