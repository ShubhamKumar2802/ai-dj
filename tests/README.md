# Tests

Mirrors `src/`'s package structure 1:1 — e.g.
`src/ingestion/feature_extractor.py` → `tests/ingestion/test_feature_extractor.py`.

pytest auto-discovers `test_*.py` files (`testpaths = ["tests"]` in
`pyproject.toml`); no `__init__.py` needed.
