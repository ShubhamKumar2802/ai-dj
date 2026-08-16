from dataclasses import dataclass

import essentia.standard as es
import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.schema import PerBarFeatures

# LoudnessEBUR128's own default hopSize (s) for its momentaryLoudness series.
_MOMENTARY_HOP_S = 0.1

# Floor to avoid log10(0) on digital silence.
_MIN_LINEAR_AMPLITUDE = 1e-9


@dataclass
class LoudnessResult:
    lufs_integrated: float
    true_peak: float
    energy_curve: list[float]


def _true_peak_dbtp(mono: np.ndarray, sample_rate: int) -> float:
    """dBTP of one channel via Essentia's `TruePeakDetector`.

    The algorithm has no scalar "peak value" output — only `peakLocations`
    (indices above a threshold) and `output` (the oversampled signal).
    True peak is `max(abs(output))`, converted to dB.
    """
    if len(mono) == 0:
        return -np.inf
    detector = es.TruePeakDetector(sampleRate=sample_rate)
    _peak_locations, output = detector(np.ascontiguousarray(mono, dtype=np.float32))
    peak_amplitude = float(np.max(np.abs(output))) if len(output) else 0.0
    return 20.0 * np.log10(max(peak_amplitude, _MIN_LINEAR_AMPLITUDE))


def _compute_true_peak(pcm: StereoPCM) -> float:
    """One scalar true_peak for a stereo signal (spec §2) — `TruePeakDetector`
    is per-channel, so this takes the max across both (the louder channel
    determines the true peak a listener/limiter would actually hit).
    """
    left = _true_peak_dbtp(pcm.samples[:, 0], pcm.sample_rate)
    right = _true_peak_dbtp(pcm.samples[:, 1], pcm.sample_rate)
    return max(left, right)


def _bar_end_times(per_bar: list[PerBarFeatures], total_duration: float) -> list[float]:
    starts = [b.start_time for b in per_bar]
    return [*starts[1:], total_duration]


def _bar_energy_curve(
    per_bar: list[PerBarFeatures],
    momentary_loudness: np.ndarray,
    total_duration: float,
) -> list[float]:
    """§8: NOT `shortTermLoudness` taken as-is (its fixed 3s window doesn't
    align to bar boundaries) — average `momentaryLoudness` within each bar's
    `[start_time, start_time + bar_duration)` window instead, one LUFS value
    per bar, aligned 1:1 with `per_bar_features` by index.
    """
    momentary_times = np.arange(len(momentary_loudness)) * _MOMENTARY_HOP_S
    ends = _bar_end_times(per_bar, total_duration)

    curve = []
    for bar, end_time in zip(per_bar, ends):
        mask = (momentary_times >= bar.start_time) & (momentary_times < end_time)
        values = momentary_loudness[mask]
        curve.append(float(np.mean(values)) if len(values) else 0.0)
    return curve


def compute_loudness(pcm: StereoPCM, per_bar: list[PerBarFeatures]) -> LoudnessResult:
    loudness_algo = es.LoudnessEBUR128(sampleRate=pcm.sample_rate, startAtZero=True)
    momentary, _short_term, integrated, _range = loudness_algo(pcm.samples)

    total_duration = pcm.samples.shape[0] / pcm.sample_rate
    energy_curve = _bar_energy_curve(per_bar, np.asarray(momentary), total_duration)

    return LoudnessResult(
        lufs_integrated=float(integrated),
        true_peak=_compute_true_peak(pcm),
        energy_curve=energy_curve,
    )
