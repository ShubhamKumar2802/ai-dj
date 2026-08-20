from ingestion.cue_derivation.derive import derive_cues
from ingestion.feature_extractor.cache import get_or_extract_features
from ingestion.orchestrator.assemble import _assemble_track
from ingestion.orchestrator.config import IngestionConfig
from ingestion.orchestrator.schema import IngestionFailure, Track


def _ingest_one(path: str, config: IngestionConfig) -> Track | IngestionFailure:
    """Spec §4. Catches Exception broadly and deliberately — audio decode/DSP
    can raise many different exception types across Essentia, librosa, and
    file I/O, and this module's whole purpose is that one bad track must not
    abort the batch. Returns a value rather than raising so orchestrate.py's
    dispatch loop needs no per-future try/except.

    Not caught here: a worker *process* crash (not a Python exception) —
    that's handled one level up, by loky's crash recovery in orchestrate.py.
    """
    try:
        raw = get_or_extract_features(path, config.feature_extractor_config)
        cue_result = derive_cues(raw, config.cue_derivation_config)
        return _assemble_track(path, raw, cue_result)
    except Exception as exc:
        return IngestionFailure(path=path, error=str(exc), error_type=type(exc).__name__)
