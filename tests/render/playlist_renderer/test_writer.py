import numpy as np
import soundfile as sf

from render.playlist_renderer import write_wav


def test_write_wav_round_trips(tmp_path, make_pcm):
    pcm = make_pcm(1.5, value=0.37)
    out_path = tmp_path / "mix.wav"

    write_wav(pcm, str(out_path))

    data, sample_rate = sf.read(str(out_path), dtype="float32")
    assert sample_rate == 48000
    assert data.ndim == 2 and data.shape[1] == 2
    assert data.shape[0] == pcm.samples.shape[0]
    # subtype="FLOAT" is 32-bit IEEE float — a bit-exact round trip.
    np.testing.assert_array_equal(data, pcm.samples)


def test_write_wav_preserves_distinct_channels(tmp_path):
    from render.transition_renderer.schema import StereoPCM

    n = 4800
    left = np.linspace(-0.5, 0.5, n, dtype=np.float32)
    right = np.linspace(0.5, -0.5, n, dtype=np.float32)
    pcm = StereoPCM(samples=np.stack([left, right], axis=1), sample_rate=48000)
    out_path = tmp_path / "stereo.wav"

    write_wav(pcm, str(out_path))
    data, _ = sf.read(str(out_path), dtype="float32")

    np.testing.assert_array_equal(data[:, 0], left)
    np.testing.assert_array_equal(data[:, 1], right)
