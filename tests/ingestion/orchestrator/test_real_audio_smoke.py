from pathlib import Path

import pytest

from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.orchestrator import IngestionConfig, ingest_tracks

# tests/ingestion/orchestrator/test_real_audio_smoke.py -> repo root is 3
# parents up (mirrors feature_extractor's own test_real_audio_smoke.py).
_MUSIC_DIR = Path(__file__).resolve().parents[3] / "music"


def _all_tracks() -> list[Path]:
    if not _MUSIC_DIR.is_dir():
        return []
    return sorted(_MUSIC_DIR.glob("*.mp3"))


pytestmark = pytest.mark.skipif(
    not _all_tracks(), reason="music/ fixture not present — real-audio smoke test skipped"
)


def test_ingest_tracks_runs_end_to_end_on_real_tracks(tmp_path):
    """The one test with genuine confidence the whole pipeline works
    together for real: real backend="loky", real get_or_extract_features/
    derive_cues, no injected fakes (spec §7). Structural sanity only — real
    music is too variable for tight value assertions here.
    """
    track_paths = [str(p) for p in _all_tracks()]
    config = IngestionConfig(
        feature_extractor_config=FeatureExtractorConfig(cache_dir=str(tmp_path / "cache")),
        cue_derivation_config=CueDerivationConfig(),
    )

    result = ingest_tracks(track_paths, config)

    assert len(result.tracks) + len(result.failures) == len(track_paths)
    for track in result.tracks:
        assert track.status in ("ok", "cut_only", "excluded")
        assert track.duration > 0
