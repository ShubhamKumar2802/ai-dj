# Implement `ingestion/feature_extractor`

## Context

`resources/documentation/overview.md`'s build-order tracker shows `ingestion/feature_extractor`
(step 1) with spec **Done** but code **—**. Its spec at
`resources/documentation/ingestion/feature_extractor/spec.md` is fully locked (file layout,
data contracts, algorithm choices all pinned — verified by reading it directly). The user has
already created `feature/ingestion-feature-extractor` off `dev` per `resources/git-convention.md`
(currently 0 commits ahead of `dev`, working tree clean). Nothing exists yet under
`src/ingestion/` or `tests/ingestion/` — this is a from-scratch build, no code to reconcile.

Goal: implement this module strictly to spec, in small buildable commits per the git
convention, ending with a PR into `dev`.

## Dependencies (new)

Add via `uv add essentia librosa numpy` (none currently declared in `pyproject.toml`).
**Do not add `madmom`** — spec §4/§15 deliberately drops it (local Xcode-license build
blocker, accepted tradeoff, not a TODO to revisit).

Risk: `essentia` can be finicky to install on macOS. PyPI has arm64/cp311 wheels for recent
`2.1b6.dev*` builds, so `uv add essentia` should resolve fine — but this must be verified for
real as the first step (`python -c "import essentia.standard as es"`). If it fails, **stop and
surface to the user** rather than silently swapping DSP libraries — that would contradict the
spec's own tooling decision (§4), which already rejected one library for a build issue.

## File layout (pinned by spec §14 — build exactly this, no deviation)

```
src/ingestion/feature_extractor/
  __init__.py            # exports: RawFeatures, PerBarFeatures, RiserCandidate,
                          #          FeatureExtractorConfig, extract_features, get_or_extract_features
  schema.py               # RawFeatures, PerBarFeatures, RiserCandidate — plain dataclasses (§2)
  config.py                # FeatureExtractorConfig, EXTRACTOR_VERSION (§5, §12)
  loader.py                 # load_canonical(path) -> StereoPCM, 48kHz float32 stereo (§3)
  content_hash.py             # hash_file(path) -> SHA-256 of raw bytes, streamed, pre-decode (§5)
  cache.py                      # get_or_extract_features() — the only real entry point (§5)
  rhythm.py                       # detect_rhythm() — bpm/beat_times/downbeats (§6)
  spectral_features.py              # compute_per_bar_features() (§7)
  loudness.py                         # compute_loudness() (§8)
  vocal_band.py                         # compute_vocal_band_energy() (§9)
  key_estimation.py                       # estimate_key() (§10)
  riser_detection.py                        # detect_risers() (§11)
  extract.py                                  # extract_features() orchestrator (§12)

tests/ingestion/feature_extractor/
  conftest.py                # synthetic click-track/tone fixtures + music/-skip-guarded real fixture
  test_loader.py, test_content_hash.py, test_cache.py, test_rhythm.py,
  test_spectral_features.py, test_loudness.py, test_vocal_band.py,
  test_key_estimation.py, test_riser_detection.py, test_extract.py
  test_real_audio_smoke.py     # pytest.mark.skipif-guarded on music/ (exists locally, gitignored)
  # no test_schema.py — plain dataclasses, no behavior (spec §13)
```

## Build order (dependency-driven)

```
schema.py + config.py  →  content_hash.py (independent)
                        →  loader.py (needs config.sample_rate)
                              → rhythm.py → spectral_features.py → loudness.py
                                                                  → vocal_band.py
                              → key_estimation.py (PCM only, independent)
                              → riser_detection.py (PCM only, frame-level, independent)
cache.py (needs only schema+config, can slot in any time after step 1)
extract.py (orchestrates everything — last)
__init__.py (re-exports finished surface — last)
```

## Commit plan

One logical unit per commit, file + its test together, matching git-convention §4.2.

**Commits are manual, not automated.** After each numbered step below is implemented and its
tests pass locally, stop and hand back to the user to review and run the `git commit`
themselves — do not run `git commit` automatically as each step finishes. Proceed to the next
step only once the user has committed (or told you to move on).

1. `chore: add essentia, librosa, numpy dependencies` — verify import works before committing
2. `feat: add feature_extractor schema and config` — `schema.py`, `config.py` (no test file per spec §13)
3. `feat: add content-hash utility` + tests — pure bytes→str, no Essentia needed
4. `test: add synthetic audio fixtures to conftest.py` — click track + tone generator (numpy → `soundfile.write` at 48kHz stereo), real-fixture skip-guard
5. `feat: add canonical audio loader` + tests — first real Essentia call, highest API-drift risk (see below)
6. `feat: add rhythm detection` + tests — RhythmExtractor2013 + librosa cross-check + 4-phase downbeat heuristic
7. `feat: add per-bar spectral feature stack` + tests
8. `feat: add loudness computation` + tests — momentary→per-bar averaging is the one piece of logic worth a dedicated isolated test (spec §13 flags this explicitly)
9. `feat: add vocal band energy` + tests
10. `feat: add key estimation` + tests — includes the 24-entry standard-notation→Camelot lookup table (doesn't exist anywhere in repo yet), tested directly with no audio needed
11. `feat: add riser detection` + tests — synthetic chirp-ending-in-transient fixture
12. `feat: add cache layer` + tests — hit/miss/version-bump-invalidation; nested-dataclass JSON round-trip (`dataclasses.asdict` → `json.dumps`, then reconstruct `PerBarFeatures`/`RiserCandidate` instances on read, not bare dicts — assert `isinstance` in the test, this is the easiest spot to get subtly wrong)
13. `feat: add extract_features orchestrator` + tests — pure glue per spec §12's 8 numbered steps
14. `feat: add feature_extractor public exports` — `__init__.py`, exact export list, mirrors `common/llm_service/__init__.py`'s explicit-`__all__` pattern
15. `test: add real-audio smoke test` — `pytest.mark.skipif`-guarded, run manually once against local `music/`

Reserve trailing `fix:`/`refactor:` commits for anything `/code-review` flags before the PR
(git-convention §4.7) — reactive, not pre-planned.

## Patterns to reuse (verified by reading the actual source)

- **Caching**: `src/common/llm_service/caching.py`'s `CachingLLMService` — `Path(cache_dir).mkdir(parents=True, exist_ok=True)`, SHA-256 hex key, one JSON file per key at `cache_dir / f"{key}.json"`. `RawFeatures` is a plain dataclass (not pydantic), so `_read`/`_write` need hand-rolled `dataclasses.asdict` + `json.dumps`/`json.loads` instead of `model_dump_json`/`model_validate_json`.
- **Config**: `src/common/llm_service/factory.py`'s config-loading shape — a `config.yaml` section keyed by module name, repo-root-relative path resolution. Add a `feature_extractor:` section to `config.yaml` alongside the existing `llm_service:` one:
  ```yaml
  feature_extractor:
    extractor_version: "1"
    cache_dir: .cache/feature_extractor
    sample_rate: 48000
  ```
  `.cache/` is already gitignored. Spec §12 only pins the `FeatureExtractorConfig` dataclass shape, not a loader-function name — don't invent a `get_feature_extractor_config()` singleton unless a real call site needs it; a hand-constructed `FeatureExtractorConfig(...)` is enough to satisfy the contract.
- **Logging**: `common.logging.get_logger(name)`, module-scope `_logger = get_logger("ai_dj.feature_extractor")`, printf-style structured log lines (as in `observability.py`).

## Implementation risks to resolve inline (not spec amendments)

Per the spec's own posture (documented decisions, not TODOs), these are implementer judgment
calls to make once and document with a comment — they do not warrant looping back to
`write-spec` unless one turns out to force an actual contract-breaking change:

- **`AudioLoader` vs `MonoLoader`**: verify actual installed-version signatures before writing `loader.py` (`help(essentia.standard.AudioLoader)`) — `MonoLoader` takes `sampleRate=` but downmixes; canonical output must stay stereo, so may need an explicit per-channel resample if `AudioLoader` doesn't take a rate.
- **`NNLSChroma`**: verify `hasattr(essentia.standard, "NNLSChroma")` on the installed version — it may only exist in `essentia.streaming`'s network/`Pool` API, which looks structurally different from the other `standard`-module calls. Check before committing to an approach.
- **`Flux`**: needs a framed spectrum sequence, not raw audio — frame the bar (document frame/hop size choice, e.g. 2048/1024), run `Spectrum()` per frame, feed consecutive pairs to `Flux()`, reduce to one scalar (document sum vs. mean choice).
- **Low/high band cutoffs** (§1.7 referenced but no Hz numbers given): reasonable choice — low ≈ 20–250 Hz (also reusable by the §6 downbeat-phase heuristic's "bass/kick" energy, so share one band-split helper rather than duplicating), high ≈ 4000–20000 Hz. Document inline.
- **`TruePeakDetector`** is typically per-channel; `RawFeatures.true_peak` is one scalar — take max across channels, document why.
- **Camelot mapping**: hand-write the 24-entry standard-notation→Camelot table, cite the standard wheel in a comment, unit test the table directly.
- **Downbeat 4-phase heuristic**: implement exactly as spec'd (§6) — `beat_times[phase::4]` per phase, mean low-band energy at those beats, pick phase maximizing contrast, confidence = normalized margin. Keep cheap; spec explicitly frames this as honestly weaker than a real DBN tracker, not something to over-engineer.

## Verification / done criteria

1. Every file in spec §14's tree exists at the exact pinned path.
2. `uv run pytest` — full suite green (synthetic-fixture tests only by default; real-audio smoke test auto-skips on a fresh clone without `music/`).
3. `uv run ruff check .` and `uv run ruff format .` clean.
4. Manual one-time real-audio sanity pass: `uv run pytest tests/ingestion/feature_extractor/test_real_audio_smoke.py -v` against local `music/` (3 Bollywood MP3s present), eyeball `bpm` against spec §4's spike reference (~130.6–130.8 BPM on the 268s track, ±2 BPM tolerance — not exact equality). Also: note `downbeat_confidence` across all 3 tracks (Q1 data point) and check on-disk cache file size via `ls -lh .cache/feature_extractor/` (Q3 data point) — both go in the PR description. Optionally a scratch `extract_features(...)` call to eyeball `lufs_integrated`/`key` plausibility.
5. No UI — not applicable (pure library module).
6. Follow git-convention §4.3–4.9 for the PR: rebase on `origin/dev`, run the three checks, push with `-u`, `gh pr create --base dev`, run `/code-review`, address findings, `gh pr merge --squash --delete-branch`.
7. Final `docs:` commit directly on synced `dev` (git-convention §4.10): flip `resources/documentation/overview.md`'s `ingestion/feature_extractor` row's Code column from `—` to `Done`.

## Open questions from spec §16 — how this build handles them

The spec itself flags three unresolved questions. None of them block starting this build —
each has a concrete way to either implement-per-current-contract or get a real data point
during this work, rather than being silently ignored:

- **Q1** (does the 4-phase downbeat heuristic's honestly-lower confidence over-quarantine
  tracks via `cue_derivation`'s D7?) — **Cannot be resolved by this module alone.**
  `cue_derivation` is spec'd but not yet implemented (overview.md: Spec Done, Code —), so D7
  quarantine doesn't exist to test against yet. This build's responsibility is only to make
  `downbeat_confidence` an honest signal (§6's phase-contrast margin, no artificial inflation)
  — during the manual real-audio smoke pass (verification step 4), eyeball the
  `downbeat_confidence` value on all 3 local tracks and note the spread as a data point for
  whoever implements `cue_derivation` next. Log this in the PR description; don't try to
  pre-solve it here.
- **Q2** (should `bpm_confidence` stay one scalar, or expose the Essentia/librosa estimates
  separately?) — **Implement per the contract as currently pinned**: §2 already commits
  `RawFeatures.bpm_confidence` to a single `float`. Build to that. If `cue_derivation`'s later
  implementation genuinely needs the two raw estimates separately, that's a real contract
  change to `RawFeatures` at that time — handled then via `write-spec` amendment, not
  speculatively now (spec's own lifecycle: don't change the contract until reality forces it).
- **Q3** (JSON cache file size at scale, given a 12-dim `chroma_vector` per bar) — **Get a real
  number instead of leaving it a guess.** Added to verification step 4 below: after running
  the real-audio smoke test, check the actual on-disk cache file size for one of the 3 local
  tracks (`ls -lh .cache/feature_extractor/`). Spec's own estimate is "a few hundred KB" —
  confirm or correct that in the PR description. If it's unexpectedly large (multi-MB), flag
  to the user before merging rather than merging silently.

## Non-goals

No `cue_derivation`, orchestrator, edge builder, or path search work — out of this spec's scope
(§1). No attempt to resolve the madmom/Xcode-license blocker (§15 already closed that). No
deviation from the pinned §14 file layout.
