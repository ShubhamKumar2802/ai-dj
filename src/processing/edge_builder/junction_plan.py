from common.contracts.schema import Envelope, Junction
from ingestion.cue_derivation.schema import Cue
from ingestion.orchestrator.schema import Track
from processing.edge_builder.config import EdgeBuilderConfig

# design-v3 §5.2's worked bass-swap example, transcribed as breakpoints over a
# 16-bar window (the default length_bars_tier2) — §6.
_TIER2_ENVELOPES = [
    Envelope(target="low", side="b", breakpoints=[(0, 0.0), (8, 0.0), (12, 1.0)]),
    Envelope(target="low", side="a", breakpoints=[(0, 1.0), (8, 1.0), (12, 0.0)]),
    Envelope(target="crossfader", side="a", breakpoints=[(0, 0.0), (12, 1.0)]),
]


def build_junction(
    track_a: Track,
    track_b: Track,
    cue_out: Cue,
    cue_in: Cue,
    tier: int,
    config: EdgeBuilderConfig,
) -> Junction:
    rate_b = 1.0
    envelopes: list[Envelope] = []

    if tier == 2:
        length_bars = config.length_bars_tier2
        rate_b = track_a.bpm / track_b.bpm
        envelopes = list(_TIER2_ENVELOPES)
    elif tier == 3:
        length_bars = 0
    elif tier == 4:
        length_bars = config.length_bars_tier4
    elif tier == 5:
        length_bars = config.length_bars_tier5
        envelopes = [
            Envelope(
                target="high",
                side="a",
                breakpoints=[(0, 0.0), (config.length_bars_tier5, 1.0)],
            )
        ]
    else:
        raise ValueError(f"unknown strategy tier: {tier}")

    return Junction(
        from_track=track_a.id,
        to_track=track_b.id,
        cue_out=cue_out.position,
        cue_in=cue_in.position,
        strategy_tier=tier,
        ramp_bars=0,
        length_bars=length_bars,
        rate_a=1.0,
        rate_b=rate_b,
        gain_db_a=0.0,
        gain_db_b=0.0,
        envelopes=envelopes,
    )
