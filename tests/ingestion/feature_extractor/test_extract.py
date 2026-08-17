import re

from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.content_hash import hash_file
from ingestion.feature_extractor.extract import extract_features


def _config(tmp_path) -> FeatureExtractorConfig:
    return FeatureExtractorConfig(cache_dir=str(tmp_path / "cache"))


def test_extract_features_populates_identity_fields(click_track_wav):
    config = _config(click_track_wav.parent)
    rf = extract_features(str(click_track_wav), config)

    assert rf.content_hash == hash_file(str(click_track_wav))
    assert rf.feature_extractor_version == config.extractor_version
    assert rf.source_path == str(click_track_wav)
    assert rf.sample_rate == config.sample_rate
    assert rf.duration > 0


def test_extract_features_per_bar_arrays_are_aligned(click_track_wav):
    config = _config(click_track_wav.parent)
    rf = extract_features(str(click_track_wav), config)

    assert len(rf.per_bar_features) > 0
    assert len(rf.energy_curve) == len(rf.per_bar_features)
    assert len(rf.vocal_band_energy) == len(rf.per_bar_features)


def test_extract_features_bpm_matches_known_fixture_bpm(click_track_wav, click_track_bpm):
    config = _config(click_track_wav.parent)
    rf = extract_features(str(click_track_wav), config)

    assert isinstance(rf.bpm, float)
    assert abs(rf.bpm - click_track_bpm) < 3.0
    assert 0.0 <= rf.bpm_confidence <= 1.0
    assert 0.0 <= rf.downbeat_confidence <= 1.0


def test_extract_features_key_is_none_or_valid_camelot(click_track_wav):
    config = _config(click_track_wav.parent)
    rf = extract_features(str(click_track_wav), config)

    if rf.key is not None:
        assert re.fullmatch(r"(1[0-2]|[1-9])[AB]", rf.key)
        assert 0.0 <= rf.key_confidence <= 1.0
    else:
        assert rf.key_confidence is None


def test_extract_features_riser_candidates_are_wired_through(riser_wav):
    # click_track_wav produces zero riser candidates (confirmed elsewhere),
    # so isinstance(..., list) alone would pass even if extract.py had a
    # wiring bug that always passed []. riser_wav reliably produces at
    # least one candidate, so this actually exercises the wiring.
    config = _config(riser_wav.parent)
    rf = extract_features(str(riser_wav), config)

    assert isinstance(rf.riser_candidates, list)
    assert len(rf.riser_candidates) >= 1
