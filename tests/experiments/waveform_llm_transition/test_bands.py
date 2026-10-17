import numpy as np
import pytest

from experiments.waveform_llm_transition.bands import normalise_pair, track_envelopes

SR = 48000


def _sine(freq_hz: float, seconds: float = 2.0, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return amplitude * np.sin(2 * np.pi * freq_hz * t)


def _envelopes(signal: np.ndarray):
    return track_envelopes(
        signal, SR, px_per_s=25, low_hz=200, high_hz=2500, order=4, bpm=120, smooth_beats=1
    )


@pytest.mark.parametrize(
    ("freq_hz", "dominant"), [(100, "low"), (1000, "mid"), (6000, "high")]
)
def test_matching_lane_dominates(freq_hz, dominant):
    env = _envelopes(_sine(freq_hz))
    # Ignore the edge columns, where the zero-phase filter's start-up lives.
    levels = {band: env.get(band)[5:-5].mean() for band in ("low", "mid", "high")}  # dB
    assert max(levels, key=levels.get) == dominant
    others = [v for band, v in levels.items() if band != dominant]
    assert levels[dominant] > max(others) + 12


def test_one_value_per_pixel_column():
    env = _envelopes(_sine(100, seconds=2.0))
    assert len(env.low) == len(env.mid) == len(env.high) == 50  # 2 s * 25 px/s


def test_stereo_is_summed_to_mono():
    mono = _sine(100)
    env_stereo = _envelopes(np.stack([mono, mono], axis=1))
    env_mono = _envelopes(mono)
    np.testing.assert_allclose(env_stereo.low, env_mono.low)


def test_shared_scale_keeps_louder_track_taller():
    loud = _envelopes(_sine(100, amplitude=0.8))
    quiet = _envelopes(_sine(100, amplitude=0.2))  # 12 dB down
    a, b = normalise_pair(loud, quiet, range_db=24)
    assert a.low[5:-5].mean() == pytest.approx(1.0, abs=0.02)
    assert b.low[5:-5].mean() == pytest.approx(0.5, abs=0.05)


def test_twice_as_energetic_low_band_draws_taller():
    # Spec "Louder low band": twice the energy is +3 dB, an eighth of a 24 dB lane.
    a_env = _envelopes(_sine(100, amplitude=0.5 * np.sqrt(2)))
    b_env = _envelopes(_sine(100, amplitude=0.5))
    a, b = normalise_pair(a_env, b_env, range_db=24)
    assert a.low[5:-5].mean() - b.low[5:-5].mean() == pytest.approx(3 / 24, abs=0.02)


def test_passage_below_window_draws_empty():
    loud = _sine(100, seconds=2.0, amplitude=0.5)
    quiet = _sine(100, seconds=2.0, amplitude=0.5 * 10 ** (-40 / 20))  # 40 dB down
    env = _envelopes(np.concatenate([loud, quiet]))
    a, _ = normalise_pair(env, env, range_db=24)
    assert a.low[10:40].min() > 0.9
    assert a.low[60:95].max() == 0.0


def test_nothing_clips_only_the_loudest_column_is_full():
    # A slow swell: every column is a different level, so only one can be the maximum.
    t = np.arange(SR * 4) / SR
    swell = (0.2 + 0.6 * t / t[-1]) * np.sin(2 * np.pi * 100 * t)
    a, b = normalise_pair(_envelopes(swell), _envelopes(0.5 * swell), range_db=24)
    assert a.low.max() == pytest.approx(1.0)
    assert np.sum(a.low >= 1.0 - 1e-9) == 1
    assert b.low.max() < 1.0


def test_heights_stay_in_lane():
    a, b = normalise_pair(_envelopes(_sine(1000)), _envelopes(_sine(6000)), range_db=24)
    for env in (a, b):
        for band in ("low", "mid", "high"):
            assert env.get(band).min() >= 0.0 and env.get(band).max() <= 1.0
