"""3-band (low / mid / high) waveform envelopes, drawn for section-level contrast.

Crossover filters rather than STFT bins: an STFT smears transients across its frame,
and transients are what show where a beat drops in. Each band's level is RMS per pixel
column, smoothed over a beat and read in dB on a window shared by both tracks of a pair
(design.md "Band split", "Shared scale within a pair").
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt

BANDS = ("low", "mid", "high")
# The level of digital silence, so log10 never sees zero.
_FLOOR_DB = -240.0


@dataclass
class BandEnvelopes:
    """One value per pixel column per band, at a fixed `px_per_s`: dB from
    `track_envelopes`, 0–1 lane heights after `normalise_pair`."""

    low: np.ndarray
    mid: np.ndarray
    high: np.ndarray
    px_per_s: float

    def get(self, band: str) -> np.ndarray:
        return getattr(self, band)


def split_bands(
    mono: np.ndarray, sample_rate: int, low_hz: float, high_hz: float, order: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zero-phase Butterworth crossover: below `low_hz`, between, above `high_hz`."""
    nyquist = sample_rate / 2
    low = sosfiltfilt(butter(order, low_hz / nyquist, btype="lowpass", output="sos"), mono)
    mid = sosfiltfilt(
        butter(order, [low_hz / nyquist, high_hz / nyquist], btype="bandpass", output="sos"), mono
    )
    high = sosfiltfilt(butter(order, high_hz / nyquist, btype="highpass", output="sos"), mono)
    return low, mid, high


def rms_envelope(signal: np.ndarray, sample_rate: int, px_per_s: float) -> np.ndarray:
    """RMS level per pixel column. The last column covers whatever partial span is left."""
    samples_per_px = sample_rate / px_per_s
    n_cols = int(np.ceil(len(signal) / samples_per_px))
    edges = np.round(np.arange(n_cols + 1) * samples_per_px).astype(int)
    edges[-1] = len(signal)
    return np.sqrt(np.add.reduceat(signal**2, edges[:-1]) / np.diff(edges))


def smoothed_db(rms: np.ndarray, px_per_s: float, bpm: float, smooth_beats: float) -> np.ndarray:
    """Average over `smooth_beats` beats, so section changes outweigh the per-kick spikes,
    then convert to dB."""
    width = max(1, round(smooth_beats * 60.0 / bpm * px_per_s))
    smoothed = uniform_filter1d(rms, width, mode="nearest")
    return np.maximum(20 * np.log10(np.maximum(smoothed, 1e-300)), _FLOOR_DB)


def track_envelopes(
    samples: np.ndarray,
    sample_rate: int,
    px_per_s: float,
    low_hz: float,
    high_hz: float,
    order: int,
    bpm: float,
    smooth_beats: float,
) -> BandEnvelopes:
    """Per-band levels in dB. `samples` is (n,) mono or (n, 2) stereo; stereo is summed
    to mono first."""
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    bands = split_bands(mono.astype(np.float64), sample_rate, low_hz, high_hz, order)
    low, mid, high = (
        smoothed_db(rms_envelope(b, sample_rate, px_per_s), px_per_s, bpm, smooth_beats)
        for b in bands
    )
    return BandEnvelopes(low=low, mid=mid, high=high, px_per_s=px_per_s)


def normalise_pair(
    a: BandEnvelopes, b: BandEnvelopes, range_db: float
) -> tuple[BandEnvelopes, BandEnvelopes]:
    """Map each band's dB levels to 0–1 lane heights on one scale shared by *both* tracks:
    the band's maximum across the pair is the top, `range_db` below it the bottom, so nothing
    clips. A louder track keeps the taller lane; anything below the window draws empty."""
    scaled = {"a": {}, "b": {}}
    for band in BANDS:
        top = max(a.get(band).max(), b.get(band).max())
        for key, env in (("a", a), ("b", b)):
            scaled[key][band] = np.clip((env.get(band) - (top - range_db)) / range_db, 0.0, 1.0)
    return (
        BandEnvelopes(**scaled["a"], px_per_s=a.px_per_s),
        BandEnvelopes(**scaled["b"], px_per_s=b.px_per_s),
    )
