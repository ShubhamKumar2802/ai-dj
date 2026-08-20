from dataclasses import dataclass, field

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.feature_extractor.config import FeatureExtractorConfig


@dataclass
class IngestionConfig:
    feature_extractor_config: FeatureExtractorConfig = field(default_factory=FeatureExtractorConfig)
    cue_derivation_config: CueDerivationConfig = field(default_factory=CueDerivationConfig)

    # None = every core. NOT passed through to joblib as-is — joblib's own
    # n_jobs=None means sequential, not "every core" (that's n_jobs=-1); the
    # translation happens in orchestrate.py (spec §5).
    max_workers: int | None = None
