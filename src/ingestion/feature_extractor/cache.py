import dataclasses
import json
import os
import time
import uuid
from pathlib import Path

from common.logging import get_logger
from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.content_hash import hash_file
from ingestion.feature_extractor.extract import extract_features
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate

_logger = get_logger("ai_dj.feature_extractor.cache")

# How often a caller waiting on another process's in-flight extraction
# re-checks for a result (spec §5, v3).
_LOCK_POLL_INTERVAL_S = 0.2

# Roughly 94x this module's own measured ~3.2s/track benchmark (spec §4) —
# generous, but finite. A lock held longer than this is treated as
# orphaned (spec §5, v3: e.g. its claimer's process crashed) and reclaimed,
# rather than waited on forever.
_LOCK_WAIT_TIMEOUT_S = 300.0


def _cache_key(content_hash: str, extractor_version: str) -> str:
    # content_hash is already a SHA-256 hash — no need to double-hash, just
    # compose deterministically with the version (spec §5's
    # (content_hash, extractor_version) key, as a single filename stem).
    return f"{content_hash}_{extractor_version}"


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _lock_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.lock"


def _try_claim(lock_path: Path) -> bool:
    """Atomically creates lock_path if it doesn't already exist (spec §5,
    v3) — the same O_CREAT|O_EXCL primitive real lockfile implementations
    use. Returns True if this call won the race."""
    try:
        os.close(os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def _read(path: Path) -> RawFeatures:
    data = json.loads(path.read_text())
    # dataclasses.asdict flattens nested dataclasses to plain dicts on
    # write — a naive RawFeatures(**data) would leave them as dicts instead
    # of PerBarFeatures/RiserCandidate instances, so reconstruct explicitly.
    data["per_bar_features"] = [PerBarFeatures(**pb) for pb in data["per_bar_features"]]
    data["riser_candidates"] = [RiserCandidate(**rc) for rc in data["riser_candidates"]]
    return RawFeatures(**data)


def _write(path: Path, raw_features: RawFeatures) -> None:
    # Write to a uniquely-named temp file, then atomically rename onto the
    # final path (spec §5, v3) — a single fixed tmp name would just move a
    # concurrent-writer race one level down; the pid+random suffix avoids
    # that. Path.replace() is atomic on both POSIX and Windows.
    tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    tmp_path.write_text(json.dumps(dataclasses.asdict(raw_features)))
    tmp_path.replace(path)


def get_or_extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures:
    """The only entry point real callers use (spec §5, v3).

    Loops: cache hit -> return. Otherwise try to claim this key; the
    winner extracts, writes atomically, and always releases the claim.
    A loser waits for the winner's result instead of redoing the
    (expensive, D6) work. A claim held past _LOCK_WAIT_TIMEOUT_S is
    treated as orphaned (e.g. its claimer's process crashed) and
    reclaimed — self-healing, not a one-shot fallback.
    """
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    content_hash = hash_file(path)
    key = _cache_key(content_hash, config.extractor_version)
    cache_path = _cache_path(cache_dir, key)
    lock_path = _lock_path(cache_dir, key)

    deadline = time.monotonic() + _LOCK_WAIT_TIMEOUT_S

    while True:
        if cache_path.exists():
            _logger.info("cache hit path=%s key=%s", path, key)
            return _read(cache_path)

        if _try_claim(lock_path):
            _logger.info("cache miss path=%s key=%s — extracting", path, key)
            start = time.monotonic()
            try:
                raw_features = extract_features(path, config)
            except Exception:
                elapsed_ms = (time.monotonic() - start) * 1000
                _logger.warning("extraction failed path=%s elapsed_ms=%.1f", path, elapsed_ms)
                raise
            finally:
                lock_path.unlink(missing_ok=True)

            elapsed_ms = (time.monotonic() - start) * 1000
            _logger.info("extraction ok path=%s elapsed_ms=%.1f", path, elapsed_ms)
            _write(cache_path, raw_features)
            return raw_features

        if time.monotonic() >= deadline:
            _logger.warning(
                "lock held > %.0fs path=%s key=%s — treating as stale, reclaiming",
                _LOCK_WAIT_TIMEOUT_S,
                path,
                key,
            )
            lock_path.unlink(missing_ok=True)
            deadline = time.monotonic() + _LOCK_WAIT_TIMEOUT_S
            continue

        time.sleep(_LOCK_POLL_INTERVAL_S)
