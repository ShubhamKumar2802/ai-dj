import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.rhythm import band_energy
from ingestion.feature_extractor.schema import PerBarFeatures

VOCAL_BAND_HZ = (300.0, 3000.0)  # D22's vocal-presence proxy band


def _bar_end_times(per_bar: list[PerBarFeatures], total_duration: float) -> list[float]:
    starts = [b.start_time for b in per_bar]
    return [*starts[1:], total_duration]


def compute_vocal_band_energy(pcm: StereoPCM, per_bar: list[PerBarFeatures]) -> list[float]:
    """Per-bar energy in the 300Hz-3kHz band (D22's proxy), one value per
    bar, aligned 1:1 with `per_bar_features` by index.

    Raw signal only — no thresholding or cost-weighting here (spec §9):
    this module's job is to compute the signal, not decide what it means.
    That interpretation is `cue_derivation`'s job, downstream.
    """
    mono = pcm.samples.mean(axis=1).astype(np.float32)
    sample_rate = pcm.sample_rate
    total_duration = pcm.samples.shape[0] / sample_rate

    ends = _bar_end_times(per_bar, total_duration)

    energies = []
    for bar, end_time in zip(per_bar, ends):
        start = int(bar.start_time * sample_rate)
        end = min(int(end_time * sample_rate), len(mono))
        start = min(start, end)
        segment = np.ascontiguousarray(mono[start:end], dtype=np.float32)
        energies.append(band_energy(segment, sample_rate, VOCAL_BAND_HZ))

    return energies
