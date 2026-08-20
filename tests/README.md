# Tests

Mirrors `src/`'s package structure 1:1 — e.g.
`src/ingestion/feature_extractor.py` → `tests/ingestion/test_feature_extractor.py`.

pytest auto-discovers `test_*.py` files (`testpaths = ["tests"]` in
`pyproject.toml`); no `__init__.py` needed, with one exception: if a new
module's test directory needs a `test_*.py` basename that already exists
under a *different* module's test directory (e.g. `ingestion/orchestrator`
and `ingestion/feature_extractor` both have their own
`test_real_audio_smoke.py`, per each module's own spec), pytest's default
import mode can't disambiguate two same-named top-level modules and errors
on collection. Fix it by adding an `__init__.py` to the new module's test
directory and every ancestor up to and including `tests/` itself (never
partial — skipping an ancestor makes the dotted module path collide with
the real `ingestion`/`common` source packages instead). Directories that
don't need disambiguation are left alone — this is opt-in per module, not a
tree-wide convention change. (`--import-mode=importlib` looks like the
obvious fix instead, but don't use it: it breaks `loky`'s pickle-by-reference
worker functions defined in test modules, silently turning
`ingestion/orchestrator`'s crash-resilience tests into false passes.)
