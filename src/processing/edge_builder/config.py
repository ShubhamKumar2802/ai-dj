from dataclasses import dataclass, field


@dataclass
class EdgeBuilderConfig:
    enabled_tiers: frozenset[int] = frozenset({2, 3, 4, 5})

    w_tempo: float = 1.0
    w_key: float = 0.8
    w_energy: float = 0.6
    w_vocal: float = 1.2
    w_cue_kind: float = 0.5
    w_phrase: float = 0.5

    tier_penalties_edm: dict[int, float] = field(
        default_factory=lambda: {2: 0.00, 3: 0.30, 4: 0.50, 5: 0.70}
    )
    tier_penalties_film: dict[int, float] = field(
        default_factory=lambda: {2: 0.10, 3: 0.00, 4: 0.10, 5: 0.50}
    )

    tempo_full_cost_ratio: float = 0.06
    tier2_max_bpm_ratio: float = 0.03
    energy_full_cost_delta: float = 6.0
    phrase_tolerance_s: float = 0.5

    length_bars_tier2: int = 16
    length_bars_tier4: int = 4
    length_bars_tier5: int = 8

    allow_half_double_time: bool = True
