import numpy as np
import pytest

from experiments.vocal_free_windows.mix import (
    SAMPLE_RATE,
    drift_ms,
    loudness_gain,
    render_cut,
    render_overlap,
    transition_span,
)
from render.transition_renderer import StereoPCM

SR = SAMPLE_RATE


def _pcm(seconds: float, value: float) -> StereoPCM:
    return StereoPCM(np.full((round(seconds * SR), 2), value, dtype=np.float32), SR)


def _ramp_pcm(seconds: float) -> StereoPCM:
    """Each sample holds its own time in seconds, so a slice reveals where it came from."""
    t = (np.arange(round(seconds * SR)) / SR).astype(np.float32)
    return StereoPCM(np.stack([t, t], axis=1), SR)


def test_cut_output_length():
    # spec "Cut output length", scaled down 10x: exit 7.5 s, B 24.7 s, entry 0.031 s
    out = render_cut(_pcm(20.0, 0.5), _pcm(24.7, 0.5), 7.5, 0.031, 132.0)
    assert out.samples.shape[0] == round(7.5 * SR) + round(24.7 * SR) - round(0.031 * SR)


def test_cut_b_starts_at_its_first_downbeat():
    b = _ramp_pcm(10.0)
    out = render_cut(_pcm(5.0, 0.0), b, 3.0, 0.31, 132.0)
    first_b = round(3.0 * SR) + round(0.005 * SR)  # past the 5 ms anti-click fade-in
    assert out.samples[first_b, 0] == pytest.approx(0.31 + 0.005, abs=1e-4)


def test_quieter_b_gain():
    gain = loudness_gain(-8.1, -12.5, match=True)
    assert 20 * np.log10(gain) == pytest.approx(4.4)
    assert loudness_gain(-8.1, -12.5, match=False) == 1.0


def test_overlap_output_length_and_a_ends():
    # spec "Overlap output length", scaled down 10x: exit 7.5 s, overlap 0.364 s
    a, b = _pcm(20.0, 0.5), _pcm(24.7, 0.0)
    out = render_overlap(a, b, 7.5, 0.031, 0.364)
    assert out.samples.shape[0] == round(7.5 * SR) + round(24.7 * SR) - round(0.031 * SR)
    nonzero = np.flatnonzero(np.abs(out.samples[:, 0]) > 1e-6)
    assert nonzero[-1] == pytest.approx(round((7.5 + 0.364) * SR), abs=2)


def test_overlap_midpoint_gains_are_equal_power():
    a, b = _pcm(10.0, 1.0), _pcm(10.0, 1.0)
    out = render_overlap(a, b, 4.0, 0.0, 2.0)
    mid = round(5.0 * SR)
    # each side at cos(pi/4) = sin(pi/4) ~ 0.707
    assert out.samples[mid, 0] == pytest.approx(2 * np.cos(np.pi / 4), abs=1e-3)


@pytest.mark.parametrize("bars, expected_ms", [(2, 36.0), (16, 287.0)])
def test_drift(bars, expected_ms):
    span = bars * 240.0 / 132.0
    assert drift_ms(span, 132.0, 130.7) == pytest.approx(expected_ms, abs=1.0)


def test_transition_span_uses_a_downbeats_then_falls_back():
    downbeats = [0.0, 2.0, 4.1, 6.0]
    assert transition_span(downbeats, 2, 2, 120.0) == pytest.approx(4.0)
    assert transition_span(downbeats, 3, 4, 120.0) == pytest.approx(8.0)  # 4 bars at 120
