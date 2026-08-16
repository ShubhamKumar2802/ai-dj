from pathlib import Path

import pytest

from ingestion.feature_extractor.cache import get_or_extract_features
from ingestion.feature_extractor.config import FeatureExtractorConfig

# tests/ingestion/feature_extractor/test_real_audio_smoke.py -> repo root
# is 3 parents up (mirrors conftest.py's _MUSIC_DIR resolution).
_MUSIC_DIR = Path(__file__).resolve().parents[3] / "music"

# Identified by duration match (268.5s), not filename — spec §4's install
# spike doesn't name its source file, only reports its duration and BPM.
_SPIKE_REFERENCE_TRACK = (
    "Subha Hone Na De 8K Full Video Song  Desi Boyz  "
    "Akshay Kumar, John Abraham  Pritam  Mika Singh.mp3"
)


def _all_tracks() -> list[Path]:
    if not _MUSIC_DIR.is_dir():
        return []
    return sorted(_MUSIC_DIR.glob("*.mp3"))


pytestmark = pytest.mark.skipif(
    not _all_tracks(), reason="music/ fixture not present — real-audio smoke test skipped"
)


def test_get_or_extract_features_runs_on_every_real_track(tmp_path):
    """Broad smoke check: the full pipeline runs end-to-end, without
    crashing, on every real track present locally. Structural sanity only —
    real music is too variable for tight value assertions here (spec §13).
    """
    config = FeatureExtractorConfig(cache_dir=str(tmp_path / "cache"))

    for track_path in _all_tracks():
        rf = get_or_extract_features(str(track_path), config)

        assert rf.duration > 0
        assert 40.0 < rf.bpm < 220.0
        assert 0.0 <= rf.bpm_confidence <= 1.0
        assert 0.0 <= rf.downbeat_confidence <= 1.0
        assert len(rf.per_bar_features) > 0
        assert len(rf.energy_curve) == len(rf.per_bar_features)
        assert len(rf.vocal_band_energy) == len(rf.per_bar_features)
        assert -60.0 < rf.lufs_integrated < 0.0
        if rf.key is not None:
            assert rf.key_confidence is not None
            assert 0.0 <= rf.key_confidence <= 1.0
        else:
            assert rf.key_confidence is None


def test_bpm_matches_spec_spike_reference(tmp_path):
    """Tight check against spec §4's install-spike numbers (130.59 BPM,
    ~130.6-130.8 range) on this specific 268s track. Confirms this
    from-scratch reimplementation reproduces the documented reference,
    not just plausible output.
    """
    track_path = _MUSIC_DIR / _SPIKE_REFERENCE_TRACK
    if not track_path.exists():
        pytest.skip("spike reference track not present locally")

    config = FeatureExtractorConfig(cache_dir=str(tmp_path / "cache"))
    rf = get_or_extract_features(str(track_path), config)

    assert abs(rf.bpm - 130.6) < 2.0
