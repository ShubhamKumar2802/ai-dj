import statistics
from typing import Literal

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.cues import bars_to_seconds
from ingestion.cue_derivation.schema import PhraseBoundary
from ingestion.feature_extractor.schema import RawFeatures


def classify_structure_template(
    raw: RawFeatures,
    free_intro_end: float,
    phrase_grid: list[PhraseBoundary],
    config: CueDerivationConfig,
) -> Literal["edm", "film", "unknown"]:
    """Spec §5 (amended combination rule) — two signals from data already in
    RawFeatures/§4's output only.

    Signal A (intro length) always votes — duration/free_intro_end are
    always defined. Signal B (phrase-spacing regularity) abstains with fewer
    than 2 phrase_grid gaps. Combine: B abstains -> A's vote; both present
    and agree -> that vote; both present and disagree -> "unknown".
    """
    intro_threshold_seconds = bars_to_seconds(config.edm_intro_bars_threshold, raw)
    intro_vote: Literal["edm", "film"] = (
        "edm" if free_intro_end >= intro_threshold_seconds else "film"
    )

    gaps = [b.bars_since_previous for b in phrase_grid if b.bars_since_previous is not None]
    if len(gaps) < 2:
        return intro_vote

    mean_gap = statistics.mean(gaps)
    coefficient_of_variation = statistics.stdev(gaps) / mean_gap if mean_gap > 0 else 0.0
    regularity_vote: Literal["edm", "film"] = (
        "edm" if coefficient_of_variation < config.phrase_regularity_cv_threshold else "film"
    )

    return intro_vote if intro_vote == regularity_vote else "unknown"
