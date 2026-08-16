import hashlib

_CHUNK_SIZE = 1024 * 1024  # 1MB


def hash_file(path: str) -> str:
    """SHA-256 of the file's raw bytes, streamed, computed before any decode.

    Deliberately over raw bytes rather than decoded PCM: a cache hit must be
    able to skip decode + DSP entirely (spec §5). Tradeoff, stated in the
    spec: an ID3-tag-only edit changes the bytes and looks like a new file —
    one redundant re-extraction, never a correctness issue.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
