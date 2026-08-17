from pathlib import Path

from ingestion.feature_extractor import cache as cache_module
from ingestion.feature_extractor.cache import get_or_extract_features
from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.schema import PerBarFeatures, RiserCandidate


def _config(tmp_path: Path, version: str = "1") -> FeatureExtractorConfig:
    return FeatureExtractorConfig(cache_dir=str(tmp_path / "cache"), extractor_version=version)


def _count_extractions(monkeypatch):
    calls = {"n": 0}
    real_extract = cache_module.extract_features

    def counting_extract(path, cfg):
        calls["n"] += 1
        return real_extract(path, cfg)

    monkeypatch.setattr(cache_module, "extract_features", counting_extract)
    return calls


def test_get_or_extract_features_cache_miss_then_hit_skips_extraction(
    click_track_wav, tmp_path, monkeypatch
):
    config = _config(tmp_path)
    calls = _count_extractions(monkeypatch)

    first = get_or_extract_features(str(click_track_wav), config)
    second = get_or_extract_features(str(click_track_wav), config)

    assert calls["n"] == 1
    assert first.bpm == second.bpm
    assert first.content_hash == second.content_hash


def test_get_or_extract_features_persists_one_json_file(click_track_wav, tmp_path):
    config = _config(tmp_path)

    get_or_extract_features(str(click_track_wav), config)

    cache_files = list(Path(config.cache_dir).glob("*.json"))
    assert len(cache_files) == 1


def test_get_or_extract_features_version_bump_invalidates_cache(
    click_track_wav, tmp_path, monkeypatch
):
    config_v1 = _config(tmp_path, version="1")
    config_v2 = _config(tmp_path, version="2")
    calls = _count_extractions(monkeypatch)

    get_or_extract_features(str(click_track_wav), config_v1)
    get_or_extract_features(str(click_track_wav), config_v2)

    assert calls["n"] == 2  # different version -> treated as a fresh miss
    cache_files = list(Path(config_v1.cache_dir).glob("*.json"))
    assert len(cache_files) == 2


def test_get_or_extract_features_round_trip_reconstructs_per_bar_features(
    click_track_wav, tmp_path
):
    # click_track_wav reliably produces non-empty per_bar_features (unlike
    # riser_wav, which produces none) — a non-vacuous list actually
    # exercises PerBarFeatures reconstruction, not just an always-true
    # `len(...) >= 0` check.
    config = _config(tmp_path)

    get_or_extract_features(str(click_track_wav), config)  # miss: writes cache
    cached = get_or_extract_features(str(click_track_wav), config)  # hit: reads cache

    assert len(cached.per_bar_features) > 0
    assert all(isinstance(b, PerBarFeatures) for b in cached.per_bar_features)


def test_get_or_extract_features_round_trip_reconstructs_riser_candidates(riser_wav, tmp_path):
    # The riser fixture reliably produces at least one candidate (verified
    # in test_riser_detection.py) — a non-empty list actually exercises
    # RiserCandidate reconstruction, not just an always-true empty check.
    config = _config(tmp_path)

    get_or_extract_features(str(riser_wav), config)  # miss: writes cache
    cached = get_or_extract_features(str(riser_wav), config)  # hit: reads cache

    assert len(cached.riser_candidates) >= 1
    assert all(isinstance(r, RiserCandidate) for r in cached.riser_candidates)


def test_get_or_extract_features_creates_cache_dir(click_track_wav, tmp_path):
    config = _config(tmp_path)
    assert not Path(config.cache_dir).exists()

    get_or_extract_features(str(click_track_wav), config)

    assert Path(config.cache_dir).is_dir()
