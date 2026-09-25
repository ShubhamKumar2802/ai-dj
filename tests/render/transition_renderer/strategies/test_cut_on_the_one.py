import numpy as np
import pytest

from render.transition_renderer.fades import FADE_MS
from render.transition_renderer.strategies.cut_on_the_one import (
    SAMPLE_RATE,
    _to_sample,
    cut_on_the_one,
)


def _n_fade(sample_rate: int = SAMPLE_RATE) -> int:
    return round(FADE_MS / 1000 * sample_rate)


def test_splice_lands_at_the_exact_sample(make_pcm, make_junction):
    # Constant-value tracks so the cut point is unambiguous.
    audio_a = make_pcm(2.0, value=0.5)
    audio_b = make_pcm(3.0, value=-0.5)
    junction = make_junction(cue_out=1.0, cue_in=0.2)

    out = cut_on_the_one(junction, audio_a, audio_b)

    s_cut = _to_sample(1.0, SAMPLE_RATE)  # 48000
    nf = _n_fade()

    # A body, before its fade-out region, is untouched 0.5.
    assert np.allclose(out.samples[: s_cut - nf], 0.5)
    # B body, after its fade-in region, is untouched -0.5 — and it begins exactly
    # at s_cut (a phantom sample either side would shift this).
    assert np.allclose(out.samples[s_cut + nf :], -0.5)
    assert out.sample_rate == SAMPLE_RATE


def test_output_length_is_a_slice_plus_b_slice(make_pcm, make_junction):
    audio_a = make_pcm(2.0, value=0.3)
    audio_b = make_pcm(3.0, value=0.3)
    junction = make_junction(cue_out=1.5, cue_in=0.5)

    out = cut_on_the_one(junction, audio_a, audio_b)

    s_cut = _to_sample(1.5, SAMPLE_RATE)
    s_in = _to_sample(0.5, SAMPLE_RATE)
    expected = s_cut + (audio_b.samples.shape[0] - s_in)  # a_slice + b_slice
    assert out.samples.shape == (expected, 2)


def test_fades_introduce_no_clipping(make_pcm, make_junction):
    audio_a = make_pcm(1.0, value=0.95)
    audio_b = make_pcm(1.0, value=-0.98)
    out = cut_on_the_one(make_junction(cue_out=0.5, cue_in=0.1), audio_a, audio_b)
    assert np.max(np.abs(out.samples)) <= 1.0


def test_fade_is_a_ramp_not_a_hard_edge(make_pcm, make_junction):
    audio_a = make_pcm(1.0, value=0.8)
    audio_b = make_pcm(1.0, value=-0.8)
    out = cut_on_the_one(make_junction(cue_out=0.5, cue_in=0.1), audio_a, audio_b)

    s_cut = _to_sample(0.5, SAMPLE_RATE)
    nf = _n_fade()

    # Endpoints of the seam are near silence...
    assert abs(out.samples[s_cut - 1, 0]) < 0.05  # A tail, faded out
    assert abs(out.samples[s_cut, 0]) < 0.05  # B head, faded in
    # ...the fade region's outer edges are still full level...
    assert out.samples[s_cut - nf, 0] == pytest.approx(0.8, abs=1e-2)
    assert out.samples[s_cut + nf - 1, 0] == pytest.approx(-0.8, abs=1e-2)
    # ...and the middle of each ramp is a partial value, not a step.
    mid_a = out.samples[s_cut - nf // 2, 0]
    assert 0.1 < mid_a < 0.7


def test_requires_48k_pcm(make_pcm, make_junction):
    good = make_pcm(1.0, value=0.2)
    wrong_rate = make_pcm(1.0, value=0.2, sample_rate=44100)
    with pytest.raises(AssertionError):
        cut_on_the_one(make_junction(), good, wrong_rate)
    with pytest.raises(AssertionError):
        cut_on_the_one(make_junction(), wrong_rate, good)
