from typing import Literal

from ingestion.cue_derivation.config import CueDerivationConfig


def quarantine(
    grid_confidence: float, config: CueDerivationConfig
) -> Literal["ok", "cut_only", "excluded"]:
    """Spec §8 — D7: "a wrong beat grid poisons every edge it touches."
    Strict `<` comparisons: a value exactly equal to a threshold does not
    quarantine."""
    if grid_confidence < config.exclude_threshold:
        return "excluded"
    if grid_confidence < config.cut_only_threshold:
        return "cut_only"
    return "ok"
