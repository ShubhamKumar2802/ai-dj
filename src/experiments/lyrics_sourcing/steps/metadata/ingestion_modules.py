"""Everything the built analysis modules produce for one file (spec §4.5).

The same two calls orchestrator/worker._ingest_one makes, called directly: there is no public
single-file ingest API, and `Track` drops per_bar_features/riser_candidates, which the
timeline needs. The feature cache makes reruns free.
"""

from experiments.lyrics_sourcing.config import MetadataConfig
from experiments.lyrics_sourcing.schema import IngestedTrack, TrackMetadata
from ingestion.cue_derivation import CueDerivationConfig, derive_cues
from ingestion.feature_extractor import FeatureExtractorConfig, get_or_extract_features


class IngestionModulesExtractor:
    def __init__(self, cfg: MetadataConfig) -> None:
        self._cfg = cfg

    def extract(self, track: IngestedTrack) -> TrackMetadata:
        raw = get_or_extract_features(track.path, FeatureExtractorConfig())
        cues = derive_cues(raw, CueDerivationConfig())
        return TrackMetadata(raw=raw, cues=cues)
