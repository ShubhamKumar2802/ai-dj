from dataclasses import dataclass

# Hand-maintained — bump on any change to extraction logic (new Essentia
# algorithm version, a changed heuristic in rhythm.py/spectral_features.py).
# Paired with content_hash as the cache key (spec §5); not auto-derived.
EXTRACTOR_VERSION = "1"


@dataclass
class FeatureExtractorConfig:
    extractor_version: str = EXTRACTOR_VERSION
    cache_dir: str = ".cache/feature_extractor"
    sample_rate: int = 48000
