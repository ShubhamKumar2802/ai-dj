import numpy as np
import pytest

from render.transition_renderer.fades import FADE_MS, linear_edge_fade

SAMPLE_RATE = 48000


def _n_fade(sample_rate: int = SAMPLE_RATE) -> int:
    return round(FADE_MS / 1000 * sample_rate)


def _constant_segment(seconds: float, value: float) -> np.ndarray:
    n = round(seconds * SAMPLE_RATE)
    return np.full((n, 2), value, dtype=np.float32)


def test_fade_out_ramps_the_tail_to_silence():
    segment = _constant_segment(1.0, 0.8)
    nf = _n_fade()

    out = linear_edge_fade(segment, SAMPLE_RATE, fade_in=False)

    assert np.allclose(out[:-nf], 0.8)  # untouched body
    assert out[-1, 0] == pytest.approx(0.0, abs=1e-2)  # ramps to ~silence
    assert out[-nf, 0] == pytest.approx(0.8, abs=1e-2)  # full level at the ramp's start


def test_fade_in_ramps_the_head_from_silence():
    segment = _constant_segment(1.0, -0.8)
    nf = _n_fade()

    out = linear_edge_fade(segment, SAMPLE_RATE, fade_in=True)

    assert np.allclose(out[nf:], -0.8)  # untouched body
    assert out[0, 0] == pytest.approx(0.0, abs=1e-2)  # starts at ~silence
    assert out[nf - 1, 0] == pytest.approx(-0.8, abs=1e-2)  # full level at the ramp's end


def test_does_not_mutate_the_input():
    segment = _constant_segment(1.0, 0.5)
    original = segment.copy()

    linear_edge_fade(segment, SAMPLE_RATE, fade_in=False)

    assert np.array_equal(segment, original)


def test_segment_shorter_than_fade_window_fades_across_its_whole_length():
    tiny = _constant_segment(0.001, 0.5)  # far shorter than FADE_MS

    out = linear_edge_fade(tiny, SAMPLE_RATE, fade_in=False)

    assert out.shape == tiny.shape
    assert np.max(np.abs(out)) <= 0.5
