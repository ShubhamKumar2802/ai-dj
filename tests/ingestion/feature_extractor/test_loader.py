import numpy as np
import soundfile as sf

from ingestion.feature_extractor.loader import CANONICAL_SAMPLE_RATE, load_canonical


def test_load_canonical_returns_48khz_stereo_float32(click_track_wav):
    pcm = load_canonical(str(click_track_wav))

    assert pcm.sample_rate == CANONICAL_SAMPLE_RATE
    assert pcm.samples.ndim == 2
    assert pcm.samples.shape[1] == 2
    assert pcm.samples.dtype == np.float32


def test_load_canonical_resamples_non_canonical_rate(tmp_path):
    native_rate = 44100
    duration_s = 1.0
    n = int(native_rate * duration_s)
    t = np.arange(n) / native_rate
    tone = 0.3 * np.sin(2 * np.pi * 440.0 * t)
    stereo = np.stack([tone, tone], axis=1).astype(np.float32)

    path = tmp_path / "44100.wav"
    sf.write(str(path), stereo, native_rate, subtype="FLOAT")

    pcm = load_canonical(str(path))

    assert pcm.sample_rate == CANONICAL_SAMPLE_RATE
    expected_n = round(n * CANONICAL_SAMPLE_RATE / native_rate)
    assert abs(pcm.samples.shape[0] - expected_n) <= 2


def test_load_canonical_upcasts_mono_to_stereo(tmp_path):
    n = CANONICAL_SAMPLE_RATE  # 1 second
    t = np.arange(n) / CANONICAL_SAMPLE_RATE
    mono = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

    path = tmp_path / "mono.wav"
    sf.write(str(path), mono, CANONICAL_SAMPLE_RATE, subtype="FLOAT")

    pcm = load_canonical(str(path))

    assert pcm.samples.shape[1] == 2
    np.testing.assert_array_equal(pcm.samples[:, 0], pcm.samples[:, 1])


def test_load_canonical_preserves_distinct_stereo_channels(tmp_path):
    n = CANONICAL_SAMPLE_RATE
    t = np.arange(n) / CANONICAL_SAMPLE_RATE
    left = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    right = np.zeros(n, dtype=np.float32)
    stereo = np.stack([left, right], axis=1)

    path = tmp_path / "distinct_stereo.wav"
    sf.write(str(path), stereo, CANONICAL_SAMPLE_RATE, subtype="FLOAT")

    pcm = load_canonical(str(path))

    # Loading at the canonical rate must not silently downmix real stereo
    # content — left carries the tone, right stays silent.
    assert np.abs(pcm.samples[:, 0]).max() > 0.1
    assert np.abs(pcm.samples[:, 1]).max() < 1e-6
