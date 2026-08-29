import pytest

from processing.edge_builder.camelot import key_distance
from processing.path_search.config import PathSearchConfig
from processing.path_search.diversity import (
    bpm_spread_deficit,
    distinct_key_count,
    diversity_penalty,
    key_variety_deficit,
)

_K_EFF = 8
_MU = 4.0


def _edges_total_over_keys(keys):
    return sum(key_distance(a, b) for a, b in zip(keys, keys[1:]))


def _objective_key_half(keys):
    """Sigma edge_costs (key term only) + mu * diversity_penalty, BPM held constant
    so bpm_spread_deficit is a shared 1.0 and cancels out of the comparison."""
    config = PathSearchConfig()
    bpms = [124.0] * len(keys)
    penalty = diversity_penalty(bpms, keys, _K_EFF, config)
    return _edges_total_over_keys(keys) + _MU * penalty


def test_wheel_walk_beats_single_key_and_random_keys():
    single_key = ["8A"] * 8
    wheel_walk = ["8A", "9A", "10A", "11A", "12A", "1A", "2A", "3A"]
    random_keys = ["8A", "2A", "9A", "3A", "10A", "4A", "11A", "5A"]

    wheel = _objective_key_half(wheel_walk)
    assert wheel < _objective_key_half(single_key)
    assert wheel < _objective_key_half(random_keys)


def test_null_keys_collapse_to_one_bucket():
    assert distinct_key_count(["8A", None, "9A", None]) == 3
    assert distinct_key_count([None, None, None]) == 1
    assert distinct_key_count(["8A", "8A", "9A"]) == 2


def test_length_one_path_scores_one():
    config = PathSearchConfig()
    assert diversity_penalty([120.0], ["8A"], _K_EFF, config) == pytest.approx(1.0)


def test_bpm_spread_deficit_edges():
    assert bpm_spread_deficit([120.0], 8.0) == 1.0  # undefined stdev
    # stdev >= target_std saturates the clamp -> deficit 0.0.
    assert bpm_spread_deficit([100.0, 140.0], 8.0) == pytest.approx(0.0)


def test_key_variety_deficit_full_and_empty_spread():
    assert key_variety_deficit(["8A"] * 8, _K_EFF) == pytest.approx(1.0)
    assert key_variety_deficit(["8A", "9A", "10A", "11A", "12A", "1A", "2A", "3A"], _K_EFF) == (
        pytest.approx(0.0)
    )
