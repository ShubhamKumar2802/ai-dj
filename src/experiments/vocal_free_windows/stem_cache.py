"""Disk cache for separated vocal stems, keyed by `(content_hash, separator_version)`.

Keyed by the audio's content hash (not its filename), so a renamed file still hits, and by
`separator_version`, so changing the model or its settings invalidates stale stems
automatically — the same idea as the feature extractor's cache. No cross-process lock: the
experiment separates one track at a time.
"""

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from common.logging import get_logger
from ingestion.feature_extractor.content_hash import hash_file

_logger = get_logger("ai_dj.experiments.vocal_free_windows.stem_cache")

STEM_SAMPLE_RATE = 48000

# (path) -> (n_samples, 2) float32 vocal stem at STEM_SAMPLE_RATE
Separate = Callable[[str], np.ndarray]


def cache_key(content_hash: str, separator_version: str) -> str:
    return hashlib.sha256(f"{content_hash}|{separator_version}".encode()).hexdigest()


def get_or_separate(
    path: str, separator_version: str, cache_dir: str | Path, separate: Separate
) -> np.ndarray:
    """The cached vocal stem for `path`, running `separate(path)` only on a cache miss."""
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{cache_key(hash_file(path), separator_version)}.wav"

    if cache_path.exists():
        _logger.info("stem cache hit path=%s", path)
    else:
        _logger.info("stem cache miss path=%s — separating", path)
        stem = np.asarray(separate(path), dtype=np.float32)
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(f".{os.getpid()}.tmp.wav")
        sf.write(tmp_path, np.clip(stem, -1.0, 1.0), STEM_SAMPLE_RATE, subtype="PCM_16")
        os.replace(tmp_path, cache_path)

    # Always return what's on disk (16-bit, clipped), so a first run and a re-run see the
    # same stem.
    stem, _ = sf.read(cache_path, dtype="float32", always_2d=True)
    return stem
