import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.rhythm import (
    BEATS_PER_BAR,
    HIGH_BAND_HZ,
    LOW_BAND_HZ,
    _cross_check_discount,
    band_energy,
    detect_rhythm,
)


def test_detect_rhythm_estimates_known_bpm(click_track_audio, click_track_bpm):
    audio, sample_rate = click_track_audio
    result = detect_rhythm(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert abs(result.bpm - click_track_bpm) < 3.0
    assert result.beats_per_bar == BEATS_PER_BAR
    assert len(result.beat_times) > 0


def test_detect_rhythm_downbeat_confidence_low_without_bass_accent(click_track_audio):
    # Every beat is an identical click — no phase carries more bass energy
    # than another, so the heuristic should honestly report low confidence.
    audio, sample_rate = click_track_audio
    result = detect_rhythm(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert result.downbeat_confidence < 0.3


def test_detect_rhythm_downbeat_confidence_high_with_bass_accent(
    downbeat_accented_click_track_audio,
):
    audio, sample_rate = downbeat_accented_click_track_audio
    result = detect_rhythm(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert result.downbeat_confidence > 0.5


def test_detect_rhythm_downbeats_are_every_fourth_beat(downbeat_accented_click_track_audio):
    audio, sample_rate = downbeat_accented_click_track_audio
    result = detect_rhythm(StereoPCM(samples=audio, sample_rate=sample_rate))

    beat_set = set(result.beat_times)
    assert set(result.downbeat_times).issubset(beat_set)
    intervals = np.diff(result.downbeat_times)
    beat_interval = np.median(np.diff(result.beat_times))
    assert np.allclose(intervals, beat_interval * BEATS_PER_BAR, atol=beat_interval * 0.5)


def test_cross_check_discount_agreement_is_full_confidence():
    assert _cross_check_discount(128.0, 128.0) == 1.0


def test_cross_check_discount_treats_octave_error_as_agreement():
    assert _cross_check_discount(128.0, 64.0) == 1.0
    assert _cross_check_discount(128.0, 256.0) == 1.0


def test_cross_check_discount_decays_with_real_disagreement():
    assert _cross_check_discount(128.0, 100.0) == 0.0


def test_cross_check_discount_zero_bpm_is_zero_confidence():
    assert _cross_check_discount(0.0, 120.0) == 0.0


def test_band_energy_concentrates_in_expected_band():
    sample_rate = 48000
    n = sample_rate
    t = np.arange(n) / sample_rate
    low_tone = np.sin(2 * np.pi * 100.0 * t).astype(np.float32)
    high_tone = np.sin(2 * np.pi * 8000.0 * t).astype(np.float32)

    assert band_energy(low_tone, sample_rate, LOW_BAND_HZ) > band_energy(
        low_tone, sample_rate, HIGH_BAND_HZ
    )
    assert band_energy(high_tone, sample_rate, HIGH_BAND_HZ) > band_energy(
        high_tone, sample_rate, LOW_BAND_HZ
    )


def test_band_energy_empty_signal_is_zero():
    assert band_energy(np.array([]), 48000, LOW_BAND_HZ) == 0.0
