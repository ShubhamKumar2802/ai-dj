from dataclasses import dataclass

# Hand-maintained — bump on any change to derivation logic (a changed heuristic
# in phrase_grid.py/hook.py/structure_template.py). Mirrors feature_extractor's
# EXTRACTOR_VERSION pattern; not auto-derived (spec §9).
CUE_DERIVATION_VERSION = "1"


@dataclass
class CueDerivationConfig:
    cue_derivation_version: str = CUE_DERIVATION_VERSION

    time_box_bars: int = 32
    hook_min_bars: int = 8
    edm_intro_bars_threshold: int = 8

    # status quarantine (spec §8) — resolved 2026-08-18, see spec's ## Amendments
    exclude_threshold: float = 0.01
    cut_only_threshold: float = 0.15

    # hook detection (spec §6) — resolved 2026-08-18, see spec's ## Amendments
    hook_high_energy_percentile: float = 0.5
    hook_high_vocal_percentile: float = 0.5
    hook_plateau_occupancy: float = 0.7
    hook_energy_drop_fraction: float = 0.25
    hook_vocal_drop_fraction: float = 0.25

    # phrase boundary detection (spec §4) — resolved 2026-08-18, see spec's ## Amendments
    phrase_boundary_novelty_std_multiplier: float = 1.0

    # structure_template classification (spec §5) — resolved 2026-08-18, see spec's ## Amendments
    phrase_regularity_cv_threshold: float = 0.3
