import numpy as np
import pytest

from ingestion.cue_derivation.schema import Cue, PhraseBoundary
from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.cost import (
    confidence_blend,
    cue_kind_cost,
    energy_cost,
    normalized_vocal_mask,
    phrase_cost,
    tempo_cost,
    vocal_cost,
)


def test_confidence_blend_endpoints():
    assert confidence_blend(raw=1.0, confidence=1.0) == pytest.approx(1.0)
    assert confidence_blend(raw=1.0, confidence=0.0) == pytest.approx(0.5)
    assert confidence_blend(raw=0.0, confidence=0.0) == pytest.approx(0.5)


def test_confidence_blend_moves_toward_half_never_toward_zero():
    # Low confidence must not make an unmeasured, high-cost pairing look cheap.
    blended = confidence_blend(raw=1.0, confidence=0.2)
    assert blended == pytest.approx(0.6)
    assert blended > 0.0


def test_tempo_cost_identical_bpm_is_free():
    config = EdgeBuilderConfig()
    assert tempo_cost(128.0, 128.0, 1.0, 1.0, config) == pytest.approx(0.0)


def test_tempo_cost_beyond_full_cost_ratio_is_maxed():
    config = EdgeBuilderConfig(allow_half_double_time=False)
    # 50% off is far past the default 6% full-cost ratio.
    assert tempo_cost(100.0, 150.0, 1.0, 1.0, config) == pytest.approx(1.0)


def test_tempo_cost_half_double_time_folding_scores_cheap():
    config = EdgeBuilderConfig(allow_half_double_time=True)
    assert tempo_cost(90.0, 180.0, 1.0, 1.0, config) == pytest.approx(0.0)


def test_tempo_cost_without_half_double_time_folding_scores_expensive():
    config = EdgeBuilderConfig(allow_half_double_time=False)
    assert tempo_cost(90.0, 180.0, 1.0, 1.0, config) == pytest.approx(1.0)


def test_tempo_cost_low_confidence_blends_toward_half():
    config = EdgeBuilderConfig()
    raw = tempo_cost(100.0, 150.0, 1.0, 1.0, config)
    blended = tempo_cost(100.0, 150.0, 0.0, 1.0, config)
    assert raw == pytest.approx(1.0)
    assert blended == pytest.approx(0.5)


def test_energy_cost_endpoints():
    config = EdgeBuilderConfig()
    assert energy_cost(0.5, 0.5, config) == pytest.approx(0.0)
    assert energy_cost(0.0, config.energy_full_cost_delta, config) == pytest.approx(1.0)


def test_energy_cost_clamped_to_one():
    config = EdgeBuilderConfig()
    assert energy_cost(0.0, config.energy_full_cost_delta * 10, config) == pytest.approx(1.0)


def test_energy_cost_is_absolute_not_signed():
    config = EdgeBuilderConfig()
    up = energy_cost(0.0, 3.0, config)
    down = energy_cost(3.0, 0.0, config)
    assert up == pytest.approx(down)


def test_vocal_cost_matches_d22_formula():
    # D22: each side normalised against its own 95th percentile, then halved.
    vocal_mask_a = [0.0, 1.0, 2.0, 3.0, 10.0]
    vocal_mask_b = [0.0, 0.0, 0.0, 0.0, 0.0]
    normalized_a = normalized_vocal_mask(vocal_mask_a)
    normalized_b = normalized_vocal_mask(vocal_mask_b)

    p95_a = np.percentile(vocal_mask_a, 95)
    expected_normalized_a_at_2 = vocal_mask_a[2] / p95_a
    assert normalized_a[2] == pytest.approx(expected_normalized_a_at_2)
    assert normalized_b[2] == pytest.approx(0.0)

    result = vocal_cost(normalized_a[2], normalized_b[2])
    assert result == pytest.approx(min(1.0, (expected_normalized_a_at_2 + 0.0) / 2.0))


def test_vocal_cost_clamped_to_one():
    assert vocal_cost(5.0, 5.0) == pytest.approx(1.0)


def test_vocal_cost_zero_when_both_silent():
    assert vocal_cost(0.0, 0.0) == pytest.approx(0.0)


def test_normalized_vocal_mask_handles_all_zero_track():
    normalized = normalized_vocal_mask([0.0, 0.0, 0.0])
    assert np.all(normalized == 0.0)


def test_cue_kind_cost_hook_exit_to_intro_end_is_cheapest():
    cue_out = Cue(position=100.0, kind="hook_exit", confidence=1.0)
    cue_in = Cue(position=8.0, kind="intro_end", confidence=1.0)
    assert cue_kind_cost(cue_out, cue_in) == pytest.approx(0.0)


def test_cue_kind_cost_time_boxed_to_first_downbeat_is_most_expensive():
    cue_out = Cue(position=100.0, kind="time_boxed", confidence=1.0)
    cue_in = Cue(position=8.0, kind="first_downbeat", confidence=1.0)
    assert cue_kind_cost(cue_out, cue_in) == pytest.approx(1.0)


def test_cue_kind_cost_low_confidence_blends_toward_half():
    cue_out = Cue(position=100.0, kind="time_boxed", confidence=0.0)
    cue_in = Cue(position=8.0, kind="first_downbeat", confidence=0.0)
    assert cue_kind_cost(cue_out, cue_in) == pytest.approx(0.5)


def test_phrase_cost_near_boundary_on_both_sides_is_cheap():
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    grid = [PhraseBoundary(position=100.0, strength=1.0, bars_since_previous=None)]
    assert phrase_cost(100.1, grid, 100.1, grid, config) == pytest.approx(0.0)


def test_phrase_cost_no_nearby_boundary_is_maxed():
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    grid = [PhraseBoundary(position=100.0, strength=1.0, bars_since_previous=None)]
    assert phrase_cost(10.0, grid, 10.0, grid, config) == pytest.approx(1.0)


def test_phrase_cost_empty_grid_is_maxed():
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    assert phrase_cost(10.0, [], 10.0, [], config) == pytest.approx(1.0)


def test_phrase_cost_averages_across_sides():
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    near_grid = [PhraseBoundary(position=10.0, strength=0.4, bars_since_previous=None)]
    far_grid = [PhraseBoundary(position=1000.0, strength=1.0, bars_since_previous=None)]
    result = phrase_cost(10.0, near_grid, 10.0, far_grid, config)
    assert result == pytest.approx((0.6 + 1.0) / 2.0)


def test_phrase_cost_clamps_raw_novelty_strength_above_one():
    # PhraseBoundary.strength is a raw Foote-checkerboard novelty score
    # (phrase_grid.py) and routinely exceeds 1.0 on real tracks — must not
    # push this term below 0.0.
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    grid = [PhraseBoundary(position=10.0, strength=8.5, bars_since_previous=None)]
    assert phrase_cost(10.0, grid, 10.0, grid, config) == pytest.approx(0.0)


def test_phrase_cost_clamps_negative_novelty_strength():
    config = EdgeBuilderConfig(phrase_tolerance_s=0.5)
    grid = [PhraseBoundary(position=10.0, strength=-3.0, bars_since_previous=None)]
    assert phrase_cost(10.0, grid, 10.0, grid, config) == pytest.approx(1.0)
