import numpy as np

from ingestion.cue_derivation.schema import Cue, CueKind, PhraseBoundary
from processing.edge_builder.camelot import key_distance
from processing.edge_builder.config import EdgeBuilderConfig

# D27's preferred cue kinds mapped onto the real CueKind enum (§4).
_CUE_OUT_PREFERENCE: dict[CueKind, float] = {
    "hook_exit": 0.00,
    "outro_start": 0.33,
    "chorus_end": 0.50,
    "interlude_start": 0.50,
    "time_boxed": 1.00,
}

_CUE_IN_PREFERENCE: dict[CueKind, float] = {
    "intro_end": 0.00,
    "riser_start": 0.00,
    "hook_in": 0.33,
    "chorus_start": 0.50,
    "first_downbeat": 1.00,
}


def confidence_blend(raw: float | np.ndarray, confidence: float | np.ndarray):
    return confidence * raw + (1.0 - confidence) * 0.5


def tempo_cost(
    bpm_a: float | np.ndarray,
    bpm_b: float | np.ndarray,
    bpm_confidence_a: float | np.ndarray,
    bpm_confidence_b: float | np.ndarray,
    config: EdgeBuilderConfig,
) -> float | np.ndarray:
    bpm_a = np.asarray(bpm_a, dtype=float)
    bpm_b = np.asarray(bpm_b, dtype=float)

    ratio = np.abs(bpm_a - bpm_b) / bpm_a
    if config.allow_half_double_time:
        ratio = np.minimum(ratio, np.abs(bpm_a - 2.0 * bpm_b) / bpm_a)
        ratio = np.minimum(ratio, np.abs(bpm_a - bpm_b / 2.0) / bpm_a)

    raw = np.minimum(1.0, ratio / config.tempo_full_cost_ratio)
    confidence = np.minimum(bpm_confidence_a, bpm_confidence_b)
    return confidence_blend(raw, confidence)


def key_cost(
    key_a: str | None,
    key_b: str | None,
    key_confidence_a: float | None,
    key_confidence_b: float | None,
) -> float:
    raw = key_distance(key_a, key_b)
    confidence_a = key_confidence_a if key_confidence_a is not None else 0.0
    confidence_b = key_confidence_b if key_confidence_b is not None else 0.0
    confidence = min(confidence_a, confidence_b)
    return confidence_blend(raw, confidence)


def energy_cost(energy_value_a: float, energy_value_b: float, config: EdgeBuilderConfig) -> float:
    return min(1.0, abs(energy_value_a - energy_value_b) / config.energy_full_cost_delta)


def normalized_vocal_mask(vocal_mask: list[float]) -> np.ndarray:
    mask = np.asarray(vocal_mask, dtype=float)
    if mask.size == 0:
        return mask

    p95 = np.percentile(mask, 95)
    if p95 <= 0:
        return np.zeros_like(mask)
    return mask / p95


def vocal_cost(normalized_value_a: float, normalized_value_b: float) -> float:
    return min(1.0, (normalized_value_a + normalized_value_b) / 2.0)


def cue_out_preference(cue: Cue) -> float:
    return confidence_blend(_CUE_OUT_PREFERENCE[cue.kind], cue.confidence)


def cue_in_preference(cue: Cue) -> float:
    return confidence_blend(_CUE_IN_PREFERENCE[cue.kind], cue.confidence)


def cue_kind_cost(cue_out: Cue, cue_in: Cue) -> float:
    return (cue_out_preference(cue_out) + cue_in_preference(cue_in)) / 2.0


def phrase_side_cost(
    position: float, phrase_grid: list[PhraseBoundary], tolerance_s: float
) -> float:
    if not phrase_grid:
        return 1.0

    nearest = min(phrase_grid, key=lambda boundary: abs(boundary.position - position))
    if abs(nearest.position - position) > tolerance_s:
        return 1.0
    # PhraseBoundary.strength is a raw Foote-checkerboard novelty score
    # (phrase_grid.py), not a [0,1] confidence — clamp before subtracting so
    # this term keeps D26's [0,1] normalisation regardless of the novelty
    # curve's actual scale on a given track.
    return 1.0 - max(0.0, min(1.0, nearest.strength))


def phrase_cost(
    cue_out_position: float,
    phrase_grid_a: list[PhraseBoundary],
    cue_in_position: float,
    phrase_grid_b: list[PhraseBoundary],
    config: EdgeBuilderConfig,
) -> float:
    cost_out = phrase_side_cost(cue_out_position, phrase_grid_a, config.phrase_tolerance_s)
    cost_in = phrase_side_cost(cue_in_position, phrase_grid_b, config.phrase_tolerance_s)
    return (cost_out + cost_in) / 2.0
