import numpy as np

from ingestion.orchestrator.schema import Track
from processing.edge_builder.bars import position_to_bar
from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.cost import (
    cue_in_preference,
    cue_out_preference,
    key_cost,
    normalized_vocal_mask,
    phrase_side_cost,
    tempo_cost,
)
from processing.edge_builder.junction_plan import build_junction
from processing.edge_builder.schema import CostTerms, ScoredEdge, ScoredEdges
from processing.edge_builder.tiers import eligible_pool, eligible_tiers, tier_penalty

_TIERS = (2, 3, 4, 5)


def _tempo_matrix(pool: list[Track], config: EdgeBuilderConfig) -> np.ndarray:
    bpm = np.array([t.bpm for t in pool])
    bpm_confidence = np.array([t.bpm_confidence for t in pool])
    return tempo_cost(
        bpm[:, None], bpm[None, :], bpm_confidence[:, None], bpm_confidence[None, :], config
    )


def _key_matrix(pool: list[Track]) -> np.ndarray:
    n = len(pool)
    matrix = np.zeros((n, n))
    for i, track_a in enumerate(pool):
        for j, track_b in enumerate(pool):
            matrix[i, j] = key_cost(
                track_a.key, track_b.key, track_a.key_confidence, track_b.key_confidence
            )
    return matrix


def _tier_penalty_tensor(pool: list[Track], config: EdgeBuilderConfig) -> np.ndarray:
    n = len(pool)
    tensor = np.zeros((n, n, len(_TIERS)))
    for i, track_a in enumerate(pool):
        for j, track_b in enumerate(pool):
            for k, tier in enumerate(_TIERS):
                tensor[i, j, k] = tier_penalty(
                    tier, track_a.structure_template, track_b.structure_template, config
                )
    return tensor


def build_edges(tracks: list[Track], config: EdgeBuilderConfig) -> ScoredEdges:
    pool = eligible_pool(tracks)

    tempo_matrix = _tempo_matrix(pool, config)
    key_matrix = _key_matrix(pool)
    tier_penalty_tensor = _tier_penalty_tensor(pool, config)

    out_bars = [[position_to_bar(c.position, t) for c in t.cue_outs] for t in pool]
    in_bars = [[position_to_bar(c.position, t) for c in t.cue_ins] for t in pool]
    energy_curves = [np.asarray(t.energy_curve, dtype=float) for t in pool]
    normalized_vocal = [normalized_vocal_mask(t.vocal_mask) for t in pool]
    cue_out_costs = [np.array([cue_out_preference(c) for c in t.cue_outs]) for t in pool]
    cue_in_costs = [np.array([cue_in_preference(c) for c in t.cue_ins]) for t in pool]
    phrase_out_costs = [
        np.array(
            [
                phrase_side_cost(c.position, t.phrase_grid, config.phrase_tolerance_s)
                for c in t.cue_outs
            ]
        )
        for t in pool
    ]
    phrase_in_costs = [
        np.array(
            [
                phrase_side_cost(c.position, t.phrase_grid, config.phrase_tolerance_s)
                for c in t.cue_ins
            ]
        )
        for t in pool
    ]

    edges: dict[tuple[str, str], ScoredEdge] = {}

    for i, track_a in enumerate(pool):
        for j, track_b in enumerate(pool):
            if i == j:
                continue
            if not track_a.cue_outs or not track_b.cue_ins:
                continue

            eligible = eligible_tiers(track_a, track_b, config)
            if not eligible:
                continue

            tier_mask = np.array([tier in eligible for tier in _TIERS])

            out_idx = np.array(out_bars[i])
            in_idx = np.array(in_bars[j])

            energy_cube = np.minimum(
                1.0,
                np.abs(energy_curves[i][out_idx][:, None] - energy_curves[j][in_idx][None, :])
                / config.energy_full_cost_delta,
            )
            vocal_cube = np.minimum(
                1.0,
                (normalized_vocal[i][out_idx][:, None] + normalized_vocal[j][in_idx][None, :])
                / 2.0,
            )
            cue_kind_cube = (cue_out_costs[i][:, None] + cue_in_costs[j][None, :]) / 2.0
            phrase_cube = (phrase_out_costs[i][:, None] + phrase_in_costs[j][None, :]) / 2.0

            pair_scalar = config.w_tempo * tempo_matrix[i, j] + config.w_key * key_matrix[i, j]
            weighted_cube = (
                pair_scalar
                + config.w_energy * energy_cube[:, :, None]
                + config.w_vocal * vocal_cube[:, :, None]
                + config.w_cue_kind * cue_kind_cube[:, :, None]
                + config.w_phrase * phrase_cube[:, :, None]
                + tier_penalty_tensor[i, j][None, None, :]
            )
            masked_cube = np.where(tier_mask[None, None, :], weighted_cube, np.inf)

            flat_idx = np.argmin(masked_cube)
            out_i, in_i, tier_i = (int(x) for x in np.unravel_index(flat_idx, masked_cube.shape))

            tier = _TIERS[tier_i]
            cue_out = track_a.cue_outs[out_i]
            cue_in = track_b.cue_ins[in_i]

            terms = CostTerms(
                tempo=float(tempo_matrix[i, j]),
                key=float(key_matrix[i, j]),
                energy=float(energy_cube[out_i, in_i]),
                vocal=float(vocal_cube[out_i, in_i]),
                cue_kind=float(cue_kind_cube[out_i, in_i]),
                phrase=float(phrase_cube[out_i, in_i]),
                tier_penalty=float(tier_penalty_tensor[i, j, tier_i]),
            )
            cost = (
                config.w_tempo * terms.tempo
                + config.w_key * terms.key
                + config.w_energy * terms.energy
                + config.w_vocal * terms.vocal
                + config.w_cue_kind * terms.cue_kind
                + config.w_phrase * terms.phrase
                + terms.tier_penalty
            )

            plan = build_junction(track_a, track_b, cue_out, cue_in, tier, config)

            edges[(track_a.id, track_b.id)] = ScoredEdge(
                from_track=track_a.id,
                to_track=track_b.id,
                cost=cost,
                plan=plan,
                terms=terms,
            )

    return ScoredEdges(edges=edges)
