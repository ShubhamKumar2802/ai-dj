"""Fixtures for the waveform_llm_transition experiment's pure-function tests.

matplotlib lives in the `experiments` uv dependency group, not the default install, so a
plain `uv run pytest` skips this whole directory instead of failing collection. Run it with
`uv run --group experiments pytest tests/experiments/waveform_llm_transition`.
"""

import importlib.util

if importlib.util.find_spec("matplotlib") is None:
    collect_ignore_glob = ["*"]
