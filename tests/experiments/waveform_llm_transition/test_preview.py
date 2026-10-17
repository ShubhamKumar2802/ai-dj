import numpy as np
import soundfile as sf

from experiments.waveform_llm_transition.preview import render_preview, write_preview

SR = 48000


def _ramp(seconds: float, offset: float) -> np.ndarray:
    """Stereo PCM whose value at sample i is offset + i / SR — i.e. its own time in seconds,
    so any output sample says where it came from."""
    t = offset + np.arange(int(seconds * SR), dtype=np.float64) / SR
    return np.stack([t, t], axis=1).astype(np.float32)


def test_preview_window():
    a = _ramp(200.0, offset=0.0)        # A's samples hold their own time, 0..200
    b = _ramp(100.0, offset=1000.0)     # B's hold 1000 + their time
    out = render_preview(a, b, SR, exit_time=141.0, entry_time=0.5, pre_s=20, post_s=20,
                         from_track="a", to_track="b", bpm_a=110.0)
    assert out.sample_rate == SR
    assert len(out.samples) == 40 * SR
    # Mid-clip samples, away from the 5 ms edge fades.
    assert out.samples[SR, 0] == np.float32(122.0)                 # A at 121 s + 1 s
    assert out.samples[19 * SR, 0] == np.float32(140.0)            # A at 140 s
    assert out.samples[21 * SR, 0] == np.float32(1000.0 + 1.5)     # B at 0.5 s + 1 s
    assert out.samples[39 * SR, 0] == np.float32(1000.0 + 19.5)    # B at 19.5 s


def test_window_clipped_at_track_edges():
    a = _ramp(10.0, offset=0.0)
    b = _ramp(5.0, offset=1000.0)
    out = render_preview(a, b, SR, exit_time=8.0, entry_time=2.0, pre_s=20, post_s=20,
                         from_track="a", to_track="b", bpm_a=110.0)
    assert len(out.samples) == (8 + 3) * SR


def test_written_wav_is_48k_stereo(tmp_path):
    a = _ramp(30.0, 0.0)
    out = render_preview(a, a, SR, 25.0, 1.0, 5, 5, "a", "b", 110.0)
    path = write_preview(out, tmp_path / "x" / "preview.wav")
    info = sf.info(path)
    assert (info.samplerate, info.channels, info.frames) == (SR, 2, 10 * SR)
