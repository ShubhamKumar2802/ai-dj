"""Builds a MixPlan from a Camelot-decided track order + LLM-labeled chorus
boundaries. Deliberately bypasses `edge_builder.build_edges()` and
`path_search.search_path()`/`beam.py` entirely — every track's window here is
a single, externally-decided choice (the LLM's `chorus1_end`, the Camelot
order), not a multi-candidate search, so there is nothing for the normal
cost-search machinery to do. Follows the same hand-built-`MixPlan` pattern as
`render/playlist_renderer/examples/example_render_skeleton.py`, reusing
`edge_builder.junction_plan.build_junction()` for the tier-3 field values
instead of duplicating them.

Every track enters at its own `grid_start` — including the opener, which
diverges on purpose from the normal pipeline's `TrackRef.cue_in = None`
(-> plays from sample 0) convention, for consistency across every track in
this experiment — and exits at its own `chorus1_end`, except the last track,
which gets `relax_closer()`'s musical fade-out instead of a hard chorus cut
(a deliberate asymmetry, not an oversight: see the plan this module was
built from).
"""

from common.contracts.schema import MixPlan, MixPlanConfig, TrackRef
from experiments.llm_camelot_sequencer.structure_llm import TrackStructureLabels
from ingestion.cue_derivation.schema import Cue
from ingestion.orchestrator.schema import Track
from processing.edge_builder.config import EdgeBuilderConfig
from processing.edge_builder.junction_plan import build_junction
from processing.path_search.boundaries import relax_closer
from processing.path_search.feasibility import path_is_feasible

_TIER = 3  # the only implemented render strategy (W2/W3) — no other tier to pick


def build_camelot_mix_plan(
    order: list[str],
    tracks_by_id: dict[str, Track],
    labels_by_id: dict[str, TrackStructureLabels],
    edge_config: EdgeBuilderConfig | None = None,
    closer_fade_bars: int = 4,
    min_play_seconds: float = 8.0,
) -> MixPlan:
    edge_config = edge_config or EdgeBuilderConfig()
    tracks = [tracks_by_id[tid] for tid in order]

    junctions = [
        build_junction(
            tracks[i],
            tracks[i + 1],
            cue_out=Cue(
                position=labels_by_id[order[i]].chorus1_end,
                kind="chorus_end",
                confidence=1.0,
            ),
            cue_in=Cue(position=tracks[i + 1].grid_start, kind="intro_end", confidence=1.0),
            tier=_TIER,
            config=edge_config,
        )
        for i in range(len(order) - 1)
    ]

    if not path_is_feasible(junctions, min_play_seconds):
        raise ValueError(
            "order_by_camelot produced a chain with an interior segment shorter than "
            f"min_play_seconds={min_play_seconds}s — a bad LLM boundary is the likely "
            "cause despite passing validate_structure_labels; inspect labels_by_id for "
            "the tracks flanking the short segment"
        )

    last_index = len(tracks) - 1
    track_refs: list[TrackRef] = []
    for i, track in enumerate(tracks):
        if i == last_index:
            cue_out, fade_out_bars = relax_closer(track, closer_fade_bars)
            track_refs.append(
                TrackRef(
                    id=track.id,
                    path=track.path,
                    cue_in=None,  # authoritative junctions[-1].cue_in = grid_start, set above
                    cue_out=cue_out,
                    fade_out_bars=fade_out_bars,
                    lufs_integrated=track.lufs_integrated,
                )
            )
        elif i == 0:
            track_refs.append(
                TrackRef(
                    id=track.id,
                    path=track.path,
                    cue_in=track.grid_start,  # every track enters at grid_start (module docstring)
                    cue_out=None,  # authoritative junctions[0].cue_out = chorus1_end, set above
                    fade_out_bars=None,
                    lufs_integrated=track.lufs_integrated,
                )
            )
        else:
            track_refs.append(
                TrackRef(
                    id=track.id,
                    path=track.path,
                    cue_in=None,
                    cue_out=None,
                    fade_out_bars=None,
                    lufs_integrated=track.lufs_integrated,
                )
            )

    config = MixPlanConfig(
        track_count=len(order),
        energy_arc="camelot_experiment",
        seed_track=order[0] if order else None,
        path_search={"min_play_seconds": min_play_seconds, "closer_fade_bars": closer_fade_bars},
        edge_builder=None,
    )
    return MixPlan(config=config, tracks=track_refs, junctions=junctions)
