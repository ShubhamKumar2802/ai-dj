import numpy as np
import pytest

from processing.path_search.config import PathSearchConfig
from processing.path_search.energy_arc import (
    arc_deviation,
    energy_norm,
    energy_norm_array,
    pool_energy_percentiles,
    target,
    target_curve,
    track_energy,
)


def test_track_energy_is_the_median_not_the_mean(make_track):
    # 4 near-silent bars, 20 normal bars. Median ignores the silent tail; the mean
    # would be dragged to ~-16.7.
    track = make_track(energy_curve=[-70.0] * 4 + [-6.0] * 20)
    assert track_energy(track) == pytest.approx(-6.0)


@pytest.mark.parametrize(
    "arc,p,expected",
    [
        ("arc", 0.0, 0.35),
        ("arc", 0.70, 1.0),
        ("arc", 1.0, 0.60),
        ("rise", 0.0, 0.0),
        ("rise", 0.70, 0.70),
        ("rise", 1.0, 1.0),
        ("flat", 0.0, 0.35),
        ("flat", 0.70, 0.35),
        ("flat", 1.0, 0.35),
    ],
)
def test_target_at_the_three_anchor_positions(arc, p, expected):
    config = PathSearchConfig(energy_arc=arc)
    assert target(p, config) == pytest.approx(expected)


def test_target_rejects_unknown_arc():
    with pytest.raises(ValueError):
        target(0.5, PathSearchConfig(energy_arc="parabola"))


def test_target_curve_length_and_endpoint():
    config = PathSearchConfig()
    curve = target_curve(3, config)
    assert len(curve) == 3
    assert curve[0] == pytest.approx(config.arc_start_level)
    assert curve[-1] == pytest.approx(config.arc_end_level)


def test_arc_deviation_uses_k_eff_minus_one_not_n_minus_one():
    config = PathSearchConfig()
    # A 4-track prefix whose energies trace the FINAL-K_eff=4 target exactly.
    norms = list(target_curve(4, config))
    assert arc_deviation(norms, k_eff=4, config=config) == pytest.approx(0.0)
    # Same four values, but the run really wants 15 tracks: the first four now map
    # to positions 0..3/14, far from where these energies belong.
    assert arc_deviation(norms, k_eff=15, config=config) > 0.1


def test_energy_norm_degenerate_pool_scores_one_half():
    assert energy_norm(5.0, p05=-10.0, p95=-10.0) == 0.5


def test_degenerate_pool_array_all_one_half(make_track):
    pool = [make_track(id=str(i), energy_curve=[-9.0, -9.0, -9.0]) for i in range(5)]
    assert np.all(energy_norm_array(pool) == 0.5)


def test_one_near_silent_track_does_not_flatten_the_others(make_track):
    # 20 tracks spread -25..-6 dB, plus one near-silent track. Percentile
    # normalisation keeps the -70 outlier below p05, so the other 20 still span
    # the full [0,1] range. Min-max normalisation (the rejected alternative) would
    # anchor the bottom at -70 and crush them into a narrow high band.
    spread = [make_track(id=f"s{i}", energy_curve=[float(-25 + i)] * 3) for i in range(20)]
    silent = make_track(id="silent", energy_curve=[-70.0] * 24)
    pool = spread + [silent]

    p05, p95 = pool_energy_percentiles(pool)
    assert p05 == pytest.approx(-25.0)  # the outlier sits below p05

    norms = energy_norm_array(pool)
    assert np.ptp(norms[:20]) > 0.5
    assert norms[20] == pytest.approx(0.0)  # the silent track floors at 0
