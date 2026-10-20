import numpy as np
import pytest

from experiments.vocal_free_windows.bass_swap import (
    gain_curves,
    render_bass_swap,
    skip_reason,
    split_low,
)
from experiments.vocal_free_windows.mix import SAMPLE_RATE, render_cut, render_overlap
from render.transition_renderer import StereoPCM

SR = SAMPLE_RATE


def _tones(seconds: float, low_hz: float, rest_hz: float) -> StereoPCM:
    t = np.arange(round(seconds * SR)) / SR
    mono = 0.4 * np.sin(2 * np.pi * low_hz * t) + 0.4 * np.sin(2 * np.pi * rest_hz * t)
    return StereoPCM(np.stack([mono, mono], axis=1).astype(np.float32), SR)


def _band_amplitude(signal: np.ndarray, hz: float) -> float:
    """Amplitude of the `hz` component of a mono signal (single-bin DFT)."""
    t = np.arange(len(signal)) / SR
    return float(2 * abs(np.mean(signal * np.exp(-2j * np.pi * hz * t))))


def test_split_sums_back():
    pcm = _tones(2.0, 60, 2000)
    low, rest = split_low(pcm.samples, 200)
    np.testing.assert_allclose(low + rest, pcm.samples, atol=1e-6)


def test_output_length_and_a_ends():
    # spec "Bass-swap output length", scaled down 10x: exit 7.5 s, span 2.909 s
    a = StereoPCM(np.full((20 * SR, 2), 0.5, dtype=np.float32), SR)
    b = StereoPCM(np.zeros((round(24.7 * SR), 2), dtype=np.float32), SR)
    out = render_bass_swap(a, b, 7.5, 0.031, 2.909, 1.4545, 200)
    assert out.samples.shape[0] == round(7.5 * SR) + round(24.7 * SR) - round(0.031 * SR)
    nonzero = np.flatnonzero(np.abs(out.samples[:, 0]) > 1e-4)
    assert nonzero[-1] <= round((7.5 + 2.909) * SR)


def test_swap_on_the_halfway_downbeat():
    # A: 60 Hz low + 2 kHz rest; B: 80 Hz low + 3 kHz rest. Swap 2 s into a 4 s span.
    a, b = _tones(10.0, 60, 2000), _tones(10.0, 80, 3000)
    exit_s, span_s, swap_s = 3.0, 4.0, 2.0
    out = render_bass_swap(a, b, exit_s, 0.0, span_s, swap_s, 200).samples[:, 0]

    before = out[round((exit_s + 1.0) * SR) : round((exit_s + 1.9) * SR)]
    after = out[round((exit_s + 2.1) * SR) : round((exit_s + 3.0) * SR)]
    assert _band_amplitude(before, 60) == pytest.approx(0.4, abs=0.02)
    assert _band_amplitude(before, 80) < 0.01
    assert _band_amplitude(after, 80) == pytest.approx(0.4, abs=0.02)
    assert _band_amplitude(after, 60) < 0.01


def test_rest_fades_from_and_to_silence():
    g = gain_curves(1000, 500)
    assert g["b_rest"][0] == 0.0
    assert g["a_rest"][-1] == pytest.approx(0.0, abs=0.01)
    assert g["a_low"][499] == 1.0 and g["b_low"][499] == 0.0
    assert g["a_rest"][:500].min() == 1.0 and g["b_rest"][500:].min() == 1.0


def test_not_enough_of_a_left_skips_but_others_render():
    downbeats = [i * 2.0 for i in range(50)]  # 49 bars
    exit_bar = 40  # 10 bars left
    reason = skip_reason(downbeats, exit_bar, 16)
    assert reason is not None and "10 bars" in reason and "16-bar" in reason
    assert skip_reason(downbeats, 30, 16) is None

    a, b = _tones(100.0, 60, 2000), _tones(20.0, 80, 3000)
    exit_s = downbeats[exit_bar - 1]
    assert render_cut(a, b, exit_s, 0.0, 120.0).samples.size > 0
    assert render_overlap(a, b, exit_s, 0.0, 4.0).samples.size > 0
