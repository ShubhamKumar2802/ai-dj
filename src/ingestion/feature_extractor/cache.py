import dataclasses
import json
import time
from pathlib import Path

from common.logging import get_logger
from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.content_hash import hash_file
from ingestion.feature_extractor.extract import extract_features
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate

_logger = get_logger("ai_dj.feature_extractor.cache")


def _cache_key(content_hash: str, extractor_version: str) -> str:
    # content_hash is already a SHA-256 hash — no need to double-hash, just
    # compose deterministically with the version (spec §5's
    # (content_hash, extractor_version) key, as a single filename stem).
    return f"{content_hash}_{extractor_version}"


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _read(path: Path) -> RawFeatures:
    data = json.loads(path.read_text())
    # dataclasses.asdict flattens nested dataclasses to plain dicts on
    # write — a naive RawFeatures(**data) would leave them as dicts instead
    # of PerBarFeatures/RiserCandidate instances, so reconstruct explicitly.
    data["per_bar_features"] = [PerBarFeatures(**pb) for pb in data["per_bar_features"]]
    data["riser_candidates"] = [RiserCandidate(**rc) for rc in data["riser_candidates"]]
    return RawFeatures(**data)


def _write(path: Path, raw_features: RawFeatures) -> None:
    path.write_text(json.dumps(dataclasses.asdict(raw_features)))


def get_or_extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures:
    """The only entry point real callers use (spec §5).

    1. content_hash = hash_file(path)              # cheap, no decode
    2. key = (content_hash, config.extractor_version)
    3. hit  -> load cached RawFeatures, return — no decode
       miss -> extract_features(path, config), persist under key, return
    """
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    content_hash = hash_file(path)
    key = _cache_key(content_hash, config.extractor_version)
    cache_path = _cache_path(cache_dir, key)

    if cache_path.exists():
        _logger.info("cache hit path=%s key=%s", path, key)
        return _read(cache_path)

    _logger.info("cache miss path=%s key=%s — extracting", path, key)
    start = time.monotonic()
    try:
        raw_features = extract_features(path, config)
    except Exception:
        elapsed_ms = (time.monotonic() - start) * 1000
        _logger.warning("extraction failed path=%s elapsed_ms=%.1f", path, elapsed_ms)
        raise

    elapsed_ms = (time.monotonic() - start) * 1000
    _logger.info("extraction ok path=%s elapsed_ms=%.1f", path, elapsed_ms)
    _write(cache_path, raw_features)
    return raw_features
