import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.loudness import compute_loudness
from ingestion.feature_extractor.schema import PerBarFeatures

SAMPLE_RATE = 48000


def _make_bar(start_time: float, end_time: float, bar_index: int = 0) -> PerBarFeatures:
    return PerBarFeatures(
        bar_index=bar_index,
        start_time=start_time,
        end_time=end_time,
        rms=0.0,
        spectral_centroid=0.0,
        spectral_flux=0.0,
        low_band_energy=0.0,
        high_band_energy=0.0,
        chroma_vector=[0.0] * 12,
    )


def _tone_pcm(amplitude: float, duration_s: float, freq: float = 300.0) -> StereoPCM:
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    return StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)


def test_compute_loudness_lufs_integrated_reflects_amplitude():
    quiet = _tone_pcm(0.05, 3.0)
    loud = _tone_pcm(0.5, 3.0)

    quiet_result = compute_loudness(quiet, [_make_bar(0.0, 3.0)])
    loud_result = compute_loudness(loud, [_make_bar(0.0, 3.0)])

    assert loud_result.lufs_integrated > quiet_result.lufs_integrated


def test_compute_loudness_true_peak_matches_known_amplitude_roughly():
    pcm = _tone_pcm(0.5, 1.0)
    result = compute_loudness(pcm, [_make_bar(0.0, 1.0)])

    expected_dbtp = 20 * np.log10(0.5)
    assert abs(result.true_peak - expected_dbtp) < 1.0


def test_compute_loudness_true_peak_can_exceed_0dbtp_on_inter_sample_peaks():
    # A near-full-scale square-ish wave reveals inter-sample peaks above
    # the sample-domain amplitude once oversampled — a real, expected
    # phenomenon for heavily limited masters, not a bug.
    n = SAMPLE_RATE
    t = np.arange(n) / SAMPLE_RATE
    mono = (0.98 * np.sign(np.sin(2 * np.pi * 300.0 * t))).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    pcm = StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)

    result = compute_loudness(pcm, [_make_bar(0.0, 1.0)])

    assert result.true_peak > 0.0


def test_compute_loudness_energy_curve_length_matches_per_bar():
    pcm = _tone_pcm(0.3, 4.0)
    bars = [
        _make_bar(0.0, 1.0, 0),
        _make_bar(1.0, 2.0, 1),
        _make_bar(2.0, 3.0, 2),
        _make_bar(3.0, 4.0, 3),
    ]

    result = compute_loudness(pcm, bars)

    assert len(result.energy_curve) == len(bars)


def test_compute_loudness_energy_curve_reflects_relative_loudness_per_bar():
    duration_s = 4.0
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = np.zeros(n, dtype=np.float32)
    half = n // 2
    mono[:half] = 0.02 * np.sin(2 * np.pi * 300.0 * t[:half])  # quiet first half
    mono[half:] = 0.5 * np.sin(2 * np.pi * 300.0 * t[half:])  # loud second half
    stereo = np.stack([mono, mono], axis=1)
    pcm = StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)

    bars = [_make_bar(0.0, 2.0, 0), _make_bar(2.0, 4.0, 1)]
    result = compute_loudness(pcm, bars)

    assert result.energy_curve[1] > result.energy_curve[0]


def test_compute_loudness_bar_with_no_momentary_samples_is_zero():
    pcm = _tone_pcm(0.3, 1.0)
    # A degenerate zero-width bar (start_time == end_time) has no momentary
    # loudness samples in its window — must return 0.0 rather than raising.
    bars = [_make_bar(0.0, 1.0, 0), _make_bar(1.0, 1.0, 1)]

    result = compute_loudness(pcm, bars)

    assert result.energy_curve[1] == 0.0


def test_compute_loudness_last_bar_does_not_leak_into_trailing_audio():
    # Regression test for the bug where the last bar's window used to fall
    # back to the literal end of the audio file instead of its own
    # end_time — silently pulling in any post-track content. Here the
    # track continues for 2 more (much louder) seconds after the bar ends.
    duration_s = 4.0
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = np.zeros(n, dtype=np.float32)
    bar_end_sample = int(2.0 * SAMPLE_RATE)
    mono[:bar_end_sample] = 0.02 * np.sin(2 * np.pi * 300.0 * t[:bar_end_sample])
    mono[bar_end_sample:] = 0.5 * np.sin(2 * np.pi * 300.0 * t[bar_end_sample:])
    stereo = np.stack([mono, mono], axis=1)
    pcm = StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)

    bars = [_make_bar(0.0, 2.0, 0)]
    result = compute_loudness(pcm, bars)

    # lufs_integrated covers the whole 4s file and is pulled up by the loud
    # second half. energy_curve[0] should stay much quieter, since it must
    # respect end_time=2.0 rather than leaking into the trailing audio.
    assert result.energy_curve[0] < result.lufs_integrated - 10.0
