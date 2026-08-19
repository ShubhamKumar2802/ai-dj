import threading
import time
from pathlib import Path

import pytest

from ingestion.feature_extractor import cache as cache_module
from ingestion.feature_extractor.cache import get_or_extract_features
from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.content_hash import hash_file
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate


def _config(tmp_path: Path, version: str = "1") -> FeatureExtractorConfig:
    return FeatureExtractorConfig(cache_dir=str(tmp_path / "cache"), extractor_version=version)


def _fake_track(tmp_path: Path, name: str = "track.wav") -> Path:
    # These v3 concurrency tests fake extract_features entirely (see below),
    # so the file just needs real bytes for hash_file to read — it's never
    # actually decoded.
    path = tmp_path / name
    path.write_bytes(b"fake audio bytes")
    return path


def _fake_raw_features() -> RawFeatures:
    return RawFeatures(
        content_hash="abc123",
        feature_extractor_version="1",
        source_path="fake.wav",
        duration=1.0,
        sample_rate=48000,
        bpm=120.0,
        bpm_confidence=0.5,
        beat_times=[],
        downbeat_times=[],
        downbeat_confidence=0.5,
        beats_per_bar=4,
        per_bar_features=[],
        lufs_integrated=-14.0,
        true_peak=-1.0,
        energy_curve=[],
        vocal_band_energy=[],
        key=None,
        key_confidence=None,
        riser_candidates=[],
    )


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


# --- v3: concurrency-safe caching (spec §5) ---
#
# These use a faked extract_features (not the real DSP pipeline) so the
# race window is controllable and the tests run in milliseconds, not
# seconds — the hit/miss/version-bump tests above already cover the real
# extraction path.


def test_concurrent_calls_for_same_key_extract_once(tmp_path, monkeypatch):
    config = _config(tmp_path)
    track_path = _fake_track(tmp_path)
    start_barrier = threading.Barrier(2)
    calls = {"n": 0}

    def slow_fake_extract(path, cfg):
        calls["n"] += 1
        time.sleep(0.2)  # widen the window so the losing thread observes the claim
        return _fake_raw_features()

    monkeypatch.setattr(cache_module, "extract_features", slow_fake_extract)

    results = []

    def worker():
        start_barrier.wait()  # both threads begin claiming at ~the same instant
        results.append(get_or_extract_features(str(track_path), config))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1
    assert len(results) == 2
    assert results[0].content_hash == results[1].content_hash


def test_failed_extraction_releases_lock_for_waiter(tmp_path, monkeypatch):
    config = _config(tmp_path)
    track_path = _fake_track(tmp_path)
    # Safety net, not load-bearing for correct code: bounds worst-case
    # runtime if the lock-release-on-failure path regresses, instead of
    # hanging for the real 300s default.
    monkeypatch.setattr(cache_module, "_LOCK_WAIT_TIMEOUT_S", 1.0)
    calls = {"n": 0}

    def fail_once_then_succeed(path, cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return _fake_raw_features()

    monkeypatch.setattr(cache_module, "extract_features", fail_once_then_succeed)

    with pytest.raises(RuntimeError):
        get_or_extract_features(str(track_path), config)

    # A second call must retry cleanly (the failed claim was released), not
    # hang waiting on a lock the first call never cleaned up.
    result = get_or_extract_features(str(track_path), config)

    assert calls["n"] == 2
    assert result.bpm == 120.0


def test_stale_lock_is_reclaimed_after_timeout(tmp_path, monkeypatch):
    config = _config(tmp_path)
    track_path = _fake_track(tmp_path)
    monkeypatch.setattr(cache_module, "_LOCK_WAIT_TIMEOUT_S", 0.05)
    monkeypatch.setattr(cache_module, "_LOCK_POLL_INTERVAL_S", 0.01)
    calls = {"n": 0}

    def fake_extract(path, cfg):
        calls["n"] += 1
        return _fake_raw_features()

    monkeypatch.setattr(cache_module, "extract_features", fake_extract)

    # Simulate a lock orphaned by a crashed claimer: pre-create it with no
    # corresponding cache entry.
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = cache_module._cache_key(hash_file(str(track_path)), config.extractor_version)
    lock_path = cache_module._lock_path(cache_dir, key)
    lock_path.touch()

    result = get_or_extract_features(str(track_path), config)

    assert calls["n"] == 1
    assert result.bpm == 120.0
    assert not lock_path.exists()  # reclaimed and released, not left stale again


def test_write_leaves_no_tmp_files_behind(tmp_path, monkeypatch):
    config = _config(tmp_path)
    track_path = _fake_track(tmp_path)
    monkeypatch.setattr(cache_module, "extract_features", lambda path, cfg: _fake_raw_features())

    get_or_extract_features(str(track_path), config)

    cache_files = list(Path(config.cache_dir).iterdir())
    assert [f for f in cache_files if ".tmp." in f.name] == []
    assert len([f for f in cache_files if f.suffix == ".json"]) == 1
