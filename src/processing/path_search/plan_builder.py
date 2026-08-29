import dataclasses
from collections.abc import Sequence

from common.contracts.schema import MixPlan, MixPlanConfig, TrackRef
from ingestion.orchestrator.schema import Track
from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.schema import ScoredEdges
from processing.path_search.boundaries import relax_closer
from processing.path_search.config import PathSearchConfig
from processing.path_search.feasibility import path_is_feasible


def build_mix_plan(
    track_ids: Sequence[str],
    tracks_by_id: dict[str, Track],
    edges: ScoredEdges,
    config: PathSearchConfig,
    edge_config: EdgeBuilderConfig | None,
) -> MixPlan:
    """Assemble the winning path into a self-sufficient ``MixPlan`` (spec §2, §8).

    Junctions are copied VERBATIM from ``ScoredEdge.plan`` — the reference is
    shared, never recomputed and never mutated (D4). D24 touches only the two
    genuinely unconstrained outer sides: the opener plays from ``0.0`` (its
    ``cue_in`` stays ``None``), and the closer's ``cue_out`` / ``fade_out_bars``
    come from ``relax_closer``. Every interior ``TrackRef`` leaves all three of
    ``cue_in`` / ``cue_out`` / ``fade_out_bars`` at ``None`` — its flanking
    junctions are authoritative.
    """
    ids = list(track_ids)
    junctions = [edges.edges[(ids[i], ids[i + 1])].plan for i in range(len(ids) - 1)]
    assert path_is_feasible(junctions, config.min_play_seconds), (
        "build_mix_plan received a path with a sub-min_play_seconds interior segment; "
        "the beam's feasibility filter should have rejected it"
    )

    last_index = len(ids) - 1
    track_refs: list[TrackRef] = []
    for i, track_id in enumerate(ids):
        track = tracks_by_id[track_id]
        if i == last_index:
            cue_out, fade_out_bars = relax_closer(track, config.closer_fade_bars)
        else:
            cue_out, fade_out_bars = None, None
        track_refs.append(
            TrackRef(
                id=track.id,
                path=track.path,
                cue_in=None,
                cue_out=cue_out,
                fade_out_bars=fade_out_bars,
                lufs_integrated=track.lufs_integrated,
            )
        )

    plan_config = MixPlanConfig(
        track_count=config.target_track_count,
        energy_arc=config.energy_arc,
        seed_track=config.seed_track,
        path_search=dataclasses.asdict(config),
        edge_builder=dataclasses.asdict(edge_config) if edge_config is not None else None,
    )
    return MixPlan(config=plan_config, tracks=track_refs, junctions=junctions)
