# Ingestion Orchestrator — Spec

**Layer:** `ingestion/` — third module in this layer, downstream of both
`feature_extractor` and `cue_derivation`.
**Depends on:** `resources/documentation/ingestion/feature_extractor/spec.md`'s
`RawFeatures` contract and `get_or_extract_features` entry point;
`resources/documentation/ingestion/cue_derivation/spec.md`'s
`CueDerivationResult` contract.

---

## 0. Invariant

> **This module touches audio only indirectly.** It calls
> `feature_extractor.get_or_extract_features` — the only function anywhere in
> this codebase allowed to touch raw PCM (`feature_extractor` spec §0) — and
> `cue_derivation.derive_cues`, which is metadata-only. This module itself
> decodes no audio and runs no DSP; its only job is to run those two calls
> per track, in parallel, and merge their outputs into a `Track`.

This is the module design-v3 §4's `RawFeatures → Track[]` arrow refers to —
the boundary where the pipeline stops touching audio and starts being pure
metadata math (design-v3 §4: *"Touches audio: feature extractor, both
renderers. Metadata only: everything else."* — this module sits on the
metadata-only side of that line despite calling into the one function that
touches audio, precisely because it never touches PCM itself).

---

## 1. Scope & consumers

**Boundary:** `ingest_tracks(paths: list[str], config: IngestionConfig, on_progress: OnProgress | None = None) -> IngestionResult`
takes a list of track paths and produces the `Track[]` node set that
`processing/edge_builder` (not yet specced) will consume to score pairwise
junction costs. It is the first module in this codebase with a real
concurrency requirement — every other `ingestion/`/`planning/` module
processes one track (or one metadata object) at a time.

**`Track` field origin**, so every field traces to exactly one producer
(same convention `feature_extractor`/`cue_derivation` specs use):

| `Track` field | Source |
|---|---|
| `id` | **here** — `= raw.content_hash` (§2, this module's own decision — see §10 Q1) |
| `path` | **here** — the input parameter, unchanged |
| `content_hash`, `duration`, `sample_rate` | `RawFeatures` |
| `bpm`, `bpm_confidence`, `beat_times`, `downbeat_times`, `downbeat_confidence`, `beats_per_bar` | `RawFeatures` |
| `grid_start`, `grid_confidence`, `free_intro_end` | `CueDerivationResult` |
| `phrase_length_bars`, `phrase_grid[]` | `CueDerivationResult` |
| `key`, `key_confidence` | `RawFeatures`, pass through unchanged |
| `lufs_integrated`, `true_peak`, `energy_curve[]` | `RawFeatures` |
| `vocal_mask[]` | **here** — `= raw.vocal_band_energy[]`, renamed (§3) |
| `structure_template`, `cue_ins[]`, `cue_outs[]` | `CueDerivationResult` |
| `familiarity_score`, `era`, `is_club_edit` | **here** — `None` in v1 (§3); owned by `ingestion/familiarity_scorer`, not yet built |
| `analysis_version` | **here** — composed from both upstream versions (§3) |
| `status` | `CueDerivationResult` |

**Explicitly out of scope:**

- `processing/edge_builder` and `processing/path_search` — this module's
  entire output is their input; nothing about how they consume `Track[]` is
  this spec's concern.
- `ingestion/familiarity_scorer` — not yet specced or built. Its three
  `Track` fields are set to `None` here (§3), a deferral, not a TBD.
- Any change to `feature_extractor` or `cue_derivation`'s own contracts —
  this module only calls their existing public entry points
  (`get_or_extract_features`, `derive_cues`) and never reaches into their
  internals.

---

## 2. Data contract (`schema.py`, `config.py`)

```
Track:
  id                    : str          # = content_hash (§10 Q1 — not fully
                                        # settled against design-v3's original
                                        # intent, which never defines this field)
  path                   : str
  content_hash             : str
  duration                   : float
  sample_rate                 : int

  bpm                           : float
  bpm_confidence                 : float
  beat_times                       : list[float]
  downbeat_times                     : list[float]
  downbeat_confidence                  : float
  beats_per_bar                          : int   # design-v3 §5.1 omits this from
                                                   # Track's own field list — an
                                                   # apparent oversight (§3)

  grid_start        : float
  grid_confidence      : float
  free_intro_end          : float

  phrase_length_bars           : float | None
  phrase_grid[]                   : list[PhraseBoundary]   # from cue_derivation.schema

  key           : str | None
  key_confidence   : float | None

  lufs_integrated     : float
  true_peak              : float

  energy_curve[]            : list[float]
  vocal_mask[]                 : list[float]   # = RawFeatures.vocal_band_energy,
                                                 # renamed here (§3)

  structure_template   : "edm" | "film" | "unknown"

  cue_ins[]     : list[Cue]    # from cue_derivation.schema
  cue_outs[]       : list[Cue]

  familiarity_score   : float | None   # None in v1 (§3)
  era                    : str | None   # None in v1 (§3)
  is_club_edit              : bool | None   # None in v1 (§3)

  analysis_version   : str   # composed (§3)
  status                : "ok" | "cut_only" | "excluded"

IngestionFailure:
  path        : str
  error         : str   # str(exception) — plain, picklable; never a live
                          # exception object (§5's loky backend requires
                          # return values to cross a process boundary)
  error_type      : str   # type(exception).__name__ — lets a future UI
                            # distinguish failure kinds without parsing
                            # the message string (§4)

IngestionResult:
  tracks[]      : list[Track]
  failures[]      : list[IngestionFailure]

IngestionConfig:
  feature_extractor_config   : FeatureExtractorConfig = FeatureExtractorConfig()
  cue_derivation_config         : CueDerivationConfig = CueDerivationConfig()
  max_workers                      : int | None = None   # None = every core. NOT passed
                                                            # through to joblib as-is — see
                                                            # §5, joblib's own n_jobs=None
                                                            # means sequential, not "all
                                                            # cores" (that's n_jobs=-1)
```

`PhraseBoundary` and `Cue` are reused directly from
`ingestion.cue_derivation.schema` — never redefined, the same convention
`cue_derivation` itself uses for `RawFeatures`.

**No `ORCHESTRATOR_VERSION` constant**, unlike `FeatureExtractorConfig`'s
`extractor_version` or `CueDerivationConfig`'s `cue_derivation_version` — a
deliberate divergence from the sibling-config pattern, not an oversight:
this module adds no analysis logic of its own to version (`analysis_version`
is composed entirely from its two upstream modules' versions, §3) and
produces no cached artifact that would need one.

---

## 3. Track assembly (`assemble.py`)

`_assemble_track(path: str, raw: RawFeatures, cue_result: CueDerivationResult) -> Track`
is a pure function — no I/O, fully unit-testable against synthetic
`RawFeatures`/`CueDerivationResult` fixtures. It does the field-mapping in
§1's table verbatim, plus four decisions made here rather than left implicit:

1. **`id = raw.content_hash`.** Design-v3 §5.1 lists `Track.id` but never
   defines its source. `content_hash` is already a stable, content-derived
   identity — no separate ID scheme is introduced for v1. Flagged in §10 Q1
   as not fully settled against design-v3's original intent.
2. **`vocal_mask` is a rename of `RawFeatures.vocal_band_energy`.**
   `feature_extractor` names the field `vocal_band_energy` (its own spec
   §9); design-v3's `Track` contract names it `vocal_mask`. This module is
   where that rename happens — `feature_extractor` and `cue_derivation`
   themselves never rename it.
3. **`familiarity_score`/`era`/`is_club_edit` are set to `None`.**
   `ingestion/familiarity_scorer` (design-v3 §6.1: "one call per track,
   cached forever, pure metadata") owns these fields but doesn't exist yet
   (tracker row 8). This is an explicit v1 deferral — when that module
   lands, it becomes a natural extension point (fill these three fields in
   after `_assemble_track` runs, or fold into it), not a schema change.
4. **`analysis_version = f"{raw.feature_extractor_version}+{cue_result.cue_derivation_version}"`.**
   `feature_extractor` spec §1 already states `analysis_version` is
   "composed from `feature_extractor_version` + `cue_derivation_version`"
   but never gives an exact format; this module is where that composition
   is defined. A simple `+`-joined string (e.g. `"2+1"`) — sortable-ish,
   both halves already independently meaningful version strings.

`beats_per_bar` is carried through from `RawFeatures` unchanged and added to
`Track`'s own field list (§2) — design-v3 §5.1's Track contract omits it,
which looks like an oversight: `feature_extractor` added `beats_per_bar` to
`RawFeatures` specifically "so a triple-meter track doesn't silently corrupt
every downstream bar-index computation" (F8), and `Track` is exactly what
bar-indexed downstream consumers (`edge_builder`) will read. Dropping it
here would silently reintroduce the exact bug F8 existed to prevent.

---

## 4. Per-track worker (`worker.py`)

```
_ingest_one(path: str, config: IngestionConfig) -> Track | IngestionFailure
  try:
      raw = get_or_extract_features(path, config.feature_extractor_config)
      cue_result = derive_cues(raw, config.cue_derivation_config)
      return _assemble_track(path, raw, cue_result)
  except Exception as exc:
      return IngestionFailure(path=path, error=str(exc), error_type=type(exc).__name__)
```

Catches `Exception` broadly and deliberately — audio decode/DSP can raise
many different exception types across Essentia, librosa, and file I/O, and
per design-v3's D7 ("a wrong beat grid poisons every edge it touches") this
module's whole purpose is that one bad track must not abort the batch.
Returns a value rather than raising specifically so §5's dispatch loop needs
no per-future `try`/`except` of its own — a track's outcome is fully
determined by this function's return value, not by catching something later.

**Not caught here**: a *worker process* crash (not a Python exception) is a
different failure mode entirely, and this `try`/`except` cannot catch it —
handled one level up, by `loky`'s crash recovery (§5, §6), not by this
function.

---

## 5. Concurrency & orchestration (`orchestrate.py`)

```
ProgressStatus = "queued" | "completed" | "failed"
OnProgress = Callable[[str, ProgressStatus], None]

ingest_tracks(
    paths: list[str],
    config: IngestionConfig,
    on_progress: OnProgress | None = None,
) -> IngestionResult
```

**Concurrency library: `joblib.Parallel`, `backend="loky"`.**
`common/llm_service`'s own spec (§8, "Concurrency & reliability — bounded
concurrency, not an orchestrator") already faced this exact shape of
problem — N independent, cacheable, no-cross-item-dependency jobs — for its
own batch LLM-scoring use case, and explicitly rejected Prefect: *"earns its
cost when there's a multi-step DAG with cross-step dependencies, scheduling,
or a need for a persistent run history/dashboard... without introducing a
scheduler/server dependency into a project whose whole planning stage is
otherwise millisecond-fast, in-process metadata munging."* That reasoning
still holds against Prefect here (§9). It doesn't settle the choice *within*
the non-Prefect options, though: stdlib's `concurrent.futures.ProcessPoolExecutor`
was the first candidate, but it's confirmed broken-by-design for this
module's actual risk profile — per the CPython issue tracker, a single
worker crash poisons the *entire* pool, and *"no further jobs can be
executed... until manual intervention."* `joblib`'s default backend,
`loky`, exists specifically to fix this: a *reusable executor* that detects
a crashed worker, respawns it, and keeps the pool itself usable (see §6).
Since this module processes arbitrary, possibly-corrupt audio files through
a C++-backed library (Essentia), that failure mode is a real risk, not a
hypothetical — worth the one new dependency. `joblib.Parallel(...,
return_as="generator_unordered")` separately covers the progress-streaming
need §5 was originally built around `as_completed()` for, for free, so
adopting `loky` for crash-resilience doesn't cost anything on the
progress-callback side.

**Dispatch:**

1. Dedupe `paths` by literal string equality before dispatch
   (order-preserving) — catches an accidentally-repeated path for free.
   Does **not** dedupe by audio content; see §6's second known limitation.
2. `n_jobs = -1 if config.max_workers is None else config.max_workers`,
   then `Parallel(n_jobs=n_jobs, backend="loky", return_as="generator_unordered")`.
   **Not a direct pass-through** — joblib's own `n_jobs=None` means
   *sequential* (equivalent to `n_jobs=1`), not "every core"; `-1` is
   joblib's own spelling for that. `IngestionConfig.max_workers=None`
   keeps its original, more intuitive public meaning ("every core") — this
   translation is an internal `orchestrate.py` detail, not exposed to
   callers. Getting this backwards would silently make the whole module
   run sequentially by default, defeating its entire purpose.
3. All deduped paths are submitted up front (one `delayed(_worker)(path, config)`
   per path). `on_progress(path, "queued")` fires at *submission* time for
   each — named `"queued"`, deliberately not `"started"`: with
   `max_workers < len(paths)`, most of these fire long before a worker
   actually picks the track up, so `"queued"` honestly describes what
   happened. Neither `concurrent.futures` nor `joblib` expose a "worker
   picked this up" event without extra plumbing this module doesn't need yet.
4. Results are consumed from the `return_as="generator_unordered"` generator
   as they arrive, **not** in input order — the instant each track
   finishes, it's classified as a `Track` (→ `tracks[]`,
   `on_progress(path, "completed")`) or an `IngestionFailure` (→
   `failures[]`, `on_progress(path, "failed")`). This is the right behavior
   for a live-progress UI (results shown as they actually finish), and
   downstream planning doesn't care about `tracks[]`'s order — edge
   builder/path search treat tracks as a set to search over, never a fixed
   sequence (design-v3: "not a BPM sort").
5. If `on_progress` itself raises, that exception propagates out of
   `ingest_tracks` — this module does not swallow bugs in caller-supplied
   callbacks.

**Progress scope, stated explicitly**: `on_progress` fires at **track**
granularity only. **Step**-level progress within a track (e.g. "computing
loudness now") would require `feature_extractor.extract_features()` to
report progress from inside its own rhythm/loudness/vocal/key steps — a
change to that module's own sealed contract, out of scope here. A future
`feature_extractor` spec amendment, not something this module can add
unilaterally.

**Two private, underscore-prefixed test-seam parameters**:
`_worker: Callable = _ingest_one` and `_backend: str = "loky"`. New pattern
for this codebase — no sibling module needed it, since none of them have
real concurrency. `loky` requires picklable-by-reference worker functions,
which makes injecting fakes/mocks awkward and can be flaky under pytest
(the `spawn` start method re-imports test modules in the child process).
Tests instead pass `_backend="threading"` (joblib's thread-based backend —
no pickling at all) with small local worker functions — sidesteps
multiprocessing-in-pytest flakiness for the bulk of the test suite (§7),
while one dedicated test exercises the real `backend="loky"` path.

---

## 6. Known v1 limitations

Stated explicitly rather than silently omitted, per this repo's own
"honest about weakness" convention (e.g. `feature_extractor`'s
`downbeat_confidence`):

**A worker-process crash — mitigated, not fully verified.** §4's
`try`/`except Exception` only catches well-behaved Python exceptions.
Essentia is C++-backed; a segfault or native crash on a malformed audio file
kills the *worker process*. Stdlib's `concurrent.futures.ProcessPoolExecutor`
would surface that as `BrokenProcessPool` on every pending/future
submission — poisoning the whole pool, not just the one bad track — which
is why §5 adopts `joblib`'s `loky` backend instead: a reusable executor
that's specifically designed to detect a crashed worker, respawn it, and
keep the pool itself usable. **What's confirmed**: `loky`'s own
documentation states this is exactly the problem it exists to fix, and the
pool survives across separate `Parallel()` calls without manual
teardown/recreation. **What's not yet confirmed**: whether a crash *mid-batch*
(inside a single `Parallel(..., return_as="generator_unordered")` call)
cleanly surfaces as a failure for just the affected track while the
generator keeps yielding the rest, or whether the dispatch loop needs its
own `try`/`except TerminatedWorkerError` with some bookkeeping of which
tracks never got a result. **Decision**: don't block this spec on it — this
is exactly the kind of tooling claim `feature_extractor` spec §4 grounds in
a measured spike rather than documentation alone; confirm empirically when
`orchestrate.py` is actually implemented (§10 Q4), and let that determine
the dispatch loop's exact shape.

**~~Two different paths with identical audio content are not deduped, and
can race on `feature_extractor`'s cache~~ — resolved.** `feature_extractor`
spec v3 (`resources/documentation/ingestion/feature_extractor/spec.md` §5)
fixes this at the source: `cache.py`'s `_write` now writes atomically
(temp-file + rename), and a cross-process claim (an atomically-created
`.lock` sentinel) makes a second caller for the same `content_hash` wait for
the first's result instead of redoing the extraction — bounded by a
self-healing timeout so a lock orphaned by a crashed claimer (§6's first
limitation, above) never becomes a permanent hang. This module's own
path-level dedup (§5) stays as a cheap first line of defense (catches an
accidentally-repeated literal path before either process even reaches the
cache), but the *correctness* of the two-different-paths-same-content case
no longer depends on it — `feature_extractor`'s cache is now safe under
concurrent access regardless.

---

## 7. Testing strategy

- **`test_assemble.py`** — `_assemble_track`'s field-mapping correctness
  against synthetic `RawFeatures`/`CueDerivationResult` fixtures: the
  `vocal_mask` rename, `analysis_version` composition, familiarity fields
  all `None`, `beats_per_bar` carried through. No I/O, no concurrency —
  the fastest, most direct tests in this module.
- **`test_worker.py`** — `_ingest_one`'s `try`/`except` → `IngestionFailure`
  conversion, via monkeypatched `get_or_extract_features`/`derive_cues`
  (module-level patches, called directly in-process — no real audio, no
  process pool).
- **`test_orchestrate.py`** — dispatch, partial-failure collection,
  progress-callback firing, and path-level dedup, using `_backend="threading"`
  with small local (closures allowed — threads don't pickle) fake workers
  standing in for `_worker`. **Plus one test using the real, default
  `_backend="loky"`** with a trivial *module-level* fake worker (returns a
  dummy `Track` immediately) — this is deliberate, not redundant with the
  thread-backend tests: it's the only test in the always-run suite that
  actually pickles `IngestionConfig`/`Track`/a worker function across a
  real process boundary, catching a picklability regression (e.g. a future
  non-picklable field added to either config) that the thread-backend seam
  would never exercise, without needing real audio.
- **`test_real_audio_smoke.py`** — skip-guarded on `music/`'s presence
  (gitignored, same as `feature_extractor`'s own), real `backend="loky"` +
  real `get_or_extract_features`/`derive_cues` end-to-end. The one test with
  genuine confidence that the whole pipeline works together for real, at
  the cost of needing local audio files. Also the natural place to
  empirically confirm §6/§10 Q4's open question about crash-isolation
  granularity, once there's a way to feed it a deliberately-malformed file.

---

## 8. File layout

```
src/ingestion/orchestrator/
  __init__.py             # public exports: Track, IngestionResult,
                           # IngestionFailure, IngestionConfig, ingest_tracks
  schema.py                # Track, IngestionResult, IngestionFailure (§2)
  config.py                 # IngestionConfig (§2)
  assemble.py                # _assemble_track() (§3)
  worker.py                    # _ingest_one() (§4)
  orchestrate.py                 # ingest_tracks() (§5)
  examples/
    example_ingest.py              # manual smoke script, mirrors
                                    # feature_extractor's example_extract.py —
                                    # gitignored, not part of the test suite

tests/ingestion/orchestrator/
  conftest.py               # synthetic RawFeatures/CueDerivationResult
                             # builders — reuse feature_extractor's and
                             # cue_derivation's own schemas directly, never
                             # redefine them
  test_assemble.py            # §7
  test_worker.py                # §7
  test_orchestrate.py             # §7
  test_real_audio_smoke.py          # §7
```

**New dependency: `joblib`** (adds its `loky` backend specifically for
crash-resilient process pooling — see §5, §6). Added at implementation time
(`uv add joblib`), not part of drafting this spec.

---

## 9. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Prefect (or a similar workflow orchestrator) | `joblib.Parallel`, `backend="loky"` (§5) | Same reasoning `common/llm_service` spec §8 already used for its own near-identical N-independent-jobs shape: earns its cost only with a multi-step DAG, scheduling, or a persistent dashboard need — none of which apply here. Reconsidered specifically against the worker-crash problem (§6) too, since Prefect's task-retry could paper over it — still rejected: that's a scheduler/orchestration layer solving a problem `loky` already fixes more surgically at the pool level. |
| Stdlib `concurrent.futures.ProcessPoolExecutor` | `joblib.Parallel`, `backend="loky"` (§5) | Confirmed broken-by-design for this module's actual risk profile (processing arbitrary, possibly-corrupt audio through a C++-backed library): per the CPython issue tracker, one worker crash poisons the *entire* pool, requiring manual teardown/recreation before any further work runs. `loky` is a reusable executor purpose-built to detect and respawn a crashed worker instead (§6) — worth the one new dependency. |
| Per-step (intra-track) progress in v1 | Per-track progress only (§5) | Needs `feature_extractor.extract_features()` to report progress from inside its own steps — a change to that module's sealed contract, and a separate future spec amendment, not something this module can add unilaterally. |
| Hand-rolling crash isolation on top of stdlib (detect `BrokenProcessPool`, restart the pool, retry remaining tracks individually) | Adopt `joblib`'s `loky` backend, which already solves most of this (§5, §6) | Building this ourselves on top of stdlib would be real, disproportionate scope; `loky` gets most of the way there off the shelf. Exact crash-isolation granularity still needs empirical confirmation (§10 Q4) before treating it as fully solved. |
| Content-based duplicate dedup in *this* module (in addition to path-level dedup) | Path-level dedup only (§5); content-hash coordination happens in `feature_extractor`'s cache instead (§6, resolved via that module's own v3) | Would need an upfront hashing pass over every input file before dispatch — real cost this module doesn't need to pay, since `feature_extractor`'s cache now safely coalesces same-content work on its own regardless of which paths or how many callers reach it. |

---

## 10. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | `Track.id = content_hash` (§2, §3) is this module's own decision — design-v3 mentions `Track.id` once and never defines its source, so this isn't confirmed against the original design intent | Correctness of `id`'s meaning if design-v3 intended something else (e.g. a per-mix-run sequential index); low blast radius (one field) |
| ~~Q2~~ | ~~Two different paths with identical audio content, submitted in the same batch, can race on `feature_extractor`'s cache write (§6) — `cache.py`'s `_write` isn't atomic~~ | **Resolved** — `feature_extractor` spec v3 (§5 of that spec) adds atomic writes and a cross-process claim; see §6/§9 above |
| Q3 | Should `ingest_tracks` preserve input order in `tracks[]` (currently: whatever order `return_as="generator_unordered"` yields, §5) once a real caller exists — does anything downstream turn out to implicitly want determinism across runs for the same input? | `orchestrate.py`'s result-ordering behavior — currently justified against design-v3's "not a BPM sort" framing, unverified against an actual `edge_builder` implementation which doesn't exist yet |
| Q4 | Does `loky`'s crash recovery isolate just the affected track within a single `Parallel(..., return_as="generator_unordered")` call, letting the generator keep yielding the rest — or does the whole call raise `TerminatedWorkerError`, needing the dispatch loop to catch it and work out which tracks never got a result? (§6) | `orchestrate.py`'s exact dispatch-loop shape — confirm via a small spike (a deliberately-crashing fake worker) when this module is actually implemented, before committing to code |
