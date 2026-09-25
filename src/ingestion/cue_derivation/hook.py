import numpy as np

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.cues import bars_to_seconds
from ingestion.cue_derivation.schema import PhraseBoundary
from ingestion.feature_extractor.schema import RawFeatures


def detect_hook(
    raw: RawFeatures,
    phrase_grid: list[PhraseBoundary],
    config: CueDerivationConfig,
) -> tuple[float | None, list[float]]:
    """Returns (hook_in, hook_exit_candidates) — spec §6; hook_exit's formula
    amended 2026-09-17. hook_in may be None (no qualifying plateau found);
    hook_exit_candidates is [] whenever hook_in is None (no plateau -> no exit
    window either) or the window contains no phrase boundary. cues.py's
    preference order / guaranteed fallbacks handle both empty cases."""
    n_bars = len(raw.per_bar_features)
    if n_bars == 0:
        return None, []

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
        return None, []

    hook_in = raw.per_bar_features[plateau_start].start_time

    plateau_end = plateau_start + window
    plateau_end_time = (
        raw.per_bar_features[plateau_end].start_time
        if plateau_end < n_bars
        else raw.per_bar_features[-1].end_time
    )

    # 2026-09-17 amendment (spec §6): every phrase boundary from the plateau
    # onward, up to time_box_bars past it, becomes a candidate — no per-
    # boundary energy/vocal drop check. Reuses time_box_bars (§7's existing
    # "one structural block: intro+buildup+hook" constant, D27) rather than
    # inventing a new one: an unbounded version of this search was tried and
    # rejected during validation — on a 297s real track it picked a candidate
    # 110 bars past the plateau, 95% through the whole file, nowhere near any
    # chorus. An 8-bar bound was tried first and rejected the other way — it
    # produced zero candidates on a different real track, where the nearest
    # genuinely clean boundary was 27 bars past the plateau. time_box_bars
    # (32) covers that 27-bar case with margin while excluding the 110-bar
    # one. Ranking which candidate within the window is actually clean is
    # edge_builder's job (its vocal/phrase cost terms read the raw per-bar
    # signal at each candidate's own position, independent of anything
    # computed here); a single-bar delta check here was exactly what let a
    # breath between two sung lines pass as "the drop" (T7).
    window_end_time = plateau_end_time + bars_to_seconds(config.time_box_bars, raw)
    hook_exit_candidates = [
        boundary.position
        for boundary in phrase_grid
        if plateau_end_time <= boundary.position < window_end_time
    ]

    return hook_in, hook_exit_candidates
