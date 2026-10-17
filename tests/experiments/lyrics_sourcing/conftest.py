"""Fixtures for the lyrics_sourcing experiment's pure-function tests.

The experiment's packages live in the `experiments` uv dependency group, not the default
install, so a plain `uv run pytest` skips this whole directory instead of failing collection.
Run it with `uv run --group experiments pytest tests/experiments/lyrics_sourcing`.
"""

import importlib.util

import pytest

_EXPERIMENT_DEPS = ("rapidfuzz", "indic_transliteration")

if any(importlib.util.find_spec(dep) is None for dep in _EXPERIMENT_DEPS):
    collect_ignore_glob = ["*"]
else:
    from experiments.lyrics_sourcing.config import load_config
    from experiments.lyrics_sourcing.schema import IngestedTrack

    @pytest.fixture
    def cfg():
        return load_config()

    @pytest.fixture
    def track():
        return IngestedTrack(
            video_id="abc123",
            url="https://www.youtube.com/watch?v=abc123",
            path="music/song.mp3",
            content_hash="deadbeef",
            duration=120.0,
            raw_title="Song (Official Video)",
            title="Song",
            artist="Artist",
            album=None,
        )
