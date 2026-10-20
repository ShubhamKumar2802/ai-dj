"""Fixtures for the vocal_free_windows experiment's tests.

matplotlib and demucs live in the `experiments` uv dependency group, not the default
install, so a plain `uv run pytest` skips this whole directory instead of failing
collection. Run it with `uv run --group experiments pytest tests/experiments/vocal_free_windows`.
"""

import importlib.util

if importlib.util.find_spec("matplotlib") is None:
    collect_ignore_glob = ["*"]
