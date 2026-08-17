import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.rhythm import RhythmResult
from ingestion.feature_extractor.spectral_features import compute_per_bar_features

SAMPLE_RATE = 48000


def _make_pcm(mono: np.ndarray) -> StereoPCM:
    stereo = np.stack([mono, mono], axis=1).astype(np.float32)
    return StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)


def _tone(freq: float, duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(int(duration_s * sample_rate)) / sample_rate
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _rhythm_with_downbeats(downbeat_times: list[float]) -> RhythmResult:
    return RhythmResult(
        bpm=120.0,
        bpm_confidence=1.0,
        beat_times=downbeat_times,
        downbeat_times=downbeat_times,
        downbeat_confidence=1.0,
        beats_per_bar=4,
    )


def test_compute_per_bar_features_one_entry_per_downbeat_interval():
    mono = _tone(220.0, 4.0)
    pcm = _make_pcm(mono)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0, 3.0, 4.0])

    bars = compute_per_bar_features(pcm, rhythm)

    assert len(bars) == 4  # len(downbeat_times) - 1
    assert [b.bar_index for b in bars] == [0, 1, 2, 3]
    assert [b.start_time for b in bars] == [0.0, 1.0, 2.0, 3.0]
    assert [b.end_time for b in bars] == [1.0, 2.0, 3.0, 4.0]


def test_compute_per_bar_features_no_entries_before_first_or_after_last_downbeat():
    mono = _tone(220.0, 4.0)
    pcm = _make_pcm(mono)
    # Only 2 downbeats -> exactly 1 bar, spanning between them only.
    rhythm = _rhythm_with_downbeats([1.0, 3.0])

    bars = compute_per_bar_features(pcm, rhythm)

    assert len(bars) == 1
    assert bars[0].start_time == 1.0


def test_compute_per_bar_features_rms_reflects_loudness():
    quiet = 0.01 * _tone(220.0, 2.0) / 0.5
    loud = _tone(220.0, 2.0)
    pcm_quiet = _make_pcm(quiet)
    pcm_loud = _make_pcm(loud)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0])

    quiet_bars = compute_per_bar_features(pcm_quiet, rhythm)
    loud_bars = compute_per_bar_features(pcm_loud, rhythm)

    assert loud_bars[0].rms > quiet_bars[0].rms


def test_compute_per_bar_features_high_tone_has_higher_centroid_than_low_tone():
    low = _tone(80.0, 2.0)
    high = _tone(8000.0, 2.0)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0])

    low_bars = compute_per_bar_features(_make_pcm(low), rhythm)
    high_bars = compute_per_bar_features(_make_pcm(high), rhythm)

    assert high_bars[0].spectral_centroid > low_bars[0].spectral_centroid


def test_compute_per_bar_features_band_energy_matches_tone_frequency():
    low = _tone(80.0, 2.0)
    high = _tone(8000.0, 2.0)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0])

    low_bars = compute_per_bar_features(_make_pcm(low), rhythm)
    high_bars = compute_per_bar_features(_make_pcm(high), rhythm)

    assert low_bars[0].low_band_energy > low_bars[0].high_band_energy
    assert high_bars[0].high_band_energy > high_bars[0].low_band_energy


def test_compute_per_bar_features_chroma_vector_is_12_dim_and_nonzero():
    mono = _tone(440.0, 2.0)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0])

    bars = compute_per_bar_features(_make_pcm(mono), rhythm)

    assert len(bars[0].chroma_vector) == 12
    assert sum(bars[0].chroma_vector) > 0.0


def test_compute_per_bar_features_steady_tone_has_lower_flux_than_transient_signal(
    click_track_audio,
):
    # Regression test: Flux is stateful and must be called on every frame
    # (including frame 0, to seed its internal state) or the first recorded
    # diff compares frame 1 against Flux's uninitialized/zero state instead
    # of frame 0 — inflating flux for *every* signal, including a steady
    # tone that shouldn't have much frame-to-frame spectral change at all.
    steady = _tone(220.0, 2.0)
    rhythm = _rhythm_with_downbeats([0.0, 1.0, 2.0])
    steady_bars = compute_per_bar_features(_make_pcm(steady), rhythm)

    click_audio, click_sr = click_track_audio
    click_pcm = StereoPCM(samples=click_audio, sample_rate=click_sr)
    click_duration = click_audio.shape[0] / click_sr
    click_rhythm = _rhythm_with_downbeats([0.0, click_duration / 2, click_duration])
    click_bars = compute_per_bar_features(click_pcm, click_rhythm)

    assert steady_bars[0].spectral_flux < click_bars[0].spectral_flux


def test_compute_per_bar_features_short_bar_below_frame_size_does_not_crash():
    # A bar shorter than one STFT frame (2048 samples) — degenerate but
    # must return zeros/empty rather than raising.
    mono = _tone(220.0, 1.0)
    pcm = _make_pcm(mono)
    rhythm = _rhythm_with_downbeats([0.0, 0.001, 1.0])

    bars = compute_per_bar_features(pcm, rhythm)

    assert len(bars) == 2
    assert bars[0].spectral_flux == 0.0
    assert bars[0].chroma_vector == [0.0] * 12
