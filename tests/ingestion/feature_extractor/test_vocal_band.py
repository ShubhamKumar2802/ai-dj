import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.schema import PerBarFeatures
from ingestion.feature_extractor.vocal_band import compute_vocal_band_energy

SAMPLE_RATE = 48000


def _make_bar(start_time: float, bar_index: int = 0) -> PerBarFeatures:
    return PerBarFeatures(
        bar_index=bar_index,
        start_time=start_time,
        rms=0.0,
        spectral_centroid=0.0,
        spectral_flux=0.0,
        low_band_energy=0.0,
        high_band_energy=0.0,
        chroma_vector=[0.0] * 12,
    )


def _tone_pcm(freq: float, duration_s: float, amplitude: float = 0.5) -> StereoPCM:
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    return StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)


def test_compute_vocal_band_energy_length_matches_per_bar():
    pcm = _tone_pcm(1000.0, 4.0)
    bars = [_make_bar(0.0, 0), _make_bar(1.0, 1), _make_bar(2.0, 2), _make_bar(3.0, 3)]

    energies = compute_vocal_band_energy(pcm, bars)

    assert len(energies) == len(bars)


def test_compute_vocal_band_energy_higher_for_in_band_tone():
    in_band = _tone_pcm(1000.0, 2.0)  # within 300Hz-3kHz
    out_of_band = _tone_pcm(80.0, 2.0)  # bass range, outside the vocal band
    bars = [_make_bar(0.0)]

    in_band_energy = compute_vocal_band_energy(in_band, bars)[0]
    out_of_band_energy = compute_vocal_band_energy(out_of_band, bars)[0]

    assert in_band_energy > out_of_band_energy


def test_compute_vocal_band_energy_reflects_relative_level_per_bar():
    duration_s = 4.0
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = np.zeros(n, dtype=np.float32)
    half = n // 2
    mono[:half] = 0.02 * np.sin(2 * np.pi * 1000.0 * t[:half])  # quiet vocal-band content
    mono[half:] = 0.5 * np.sin(2 * np.pi * 1000.0 * t[half:])  # loud vocal-band content
    stereo = np.stack([mono, mono], axis=1)
    pcm = StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)

    bars = [_make_bar(0.0, 0), _make_bar(2.0, 1)]
    energies = compute_vocal_band_energy(pcm, bars)

    assert energies[1] > energies[0]


def test_compute_vocal_band_energy_empty_final_bar_is_zero():
    pcm = _tone_pcm(1000.0, 1.0)
    bars = [_make_bar(0.0, 0), _make_bar(1.0, 1)]

    energies = compute_vocal_band_energy(pcm, bars)

    assert energies[1] == 0.0
