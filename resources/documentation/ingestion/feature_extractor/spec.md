# Feature Extractor — Spec

**v3** — supersedes v2, see `archive/spec-v2.md`.

**What changed in v3** (surfaced while designing `ingestion/orchestrator`, the
first module to ever call `get_or_extract_features` concurrently — see that
module's spec §6): `cache.py`'s caching mechanism gets two fixes, both confined
to §5. (1) **Atomic writes** — `_write` was a plain `path.write_text(...)`,
no atomicity; two different processes racing to cache-write the same
`(content_hash, extractor_version)` key (identical audio content, different
paths, same batch) could corrupt the cache file via interleaved writes. Now
writes go to a uniquely-named temp file, then an atomic rename onto the final
path — corruption is now structurally impossible regardless of how many
processes race on the same key. (2) **Cross-process claim** — a concurrent
caller for the same key now waits for the first claimer's result instead of
redoing the (expensive, D6) extraction itself, via an atomically-created
`.lock` sentinel file; the wait is bounded and self-healing (§5) so a lock
orphaned by a crashed process (the crash risk `orchestrator`'s own spec
documents) never becomes a permanent hang for every future caller. This is a
version bump, not an amendment, for two reasons: §5's previous "one JSON file
per key" claim is no longer strictly true at every instant (a transient
`.lock` file can coexist during extraction) — an existing specific claim
changing, not a gap being filled — and `get_or_extract_features` gains a
genuinely new invariant (it can now legitimately block waiting on another
caller, bounded by a timeout) where before it never could. Neither change
touches `get_or_extract_features`'s signature or `RawFeatures`'s schema —
only §5's internal mechanism and its own stated guarantees.

**Layer:** `ingestion/` — first module in this layer.
**v1 tooling:** Essentia (primary DSP engine) + librosa (cross-check only). No madmom.

---

## 0. Invariant

> **This is the only ingestion module that touches raw PCM.** Every other ingestion
> module (`cue_derivation`, and everything downstream of it — edge builder, path
> search, both renderers' planning inputs) consumes only this module's output,
> `RawFeatures`, or `Track` built from it. Nothing downstream ever re-opens the audio
> file.

This makes design-v3 §4's "Touches audio: feature extractor, both renderers. Metadata
only: everything else" mechanically true rather than conventional, the same way
`llm_service`'s §0 invariant keeps D14 true. `RawFeatures` must be complete enough that
`cue_derivation` (metadata-only, milliseconds, rerun constantly per D6) never needs to
decode audio to do its job.

---

## 1. Scope & consumers

**Boundary:** `extract_features(path) -> RawFeatures` is audio-touching, expensive
(decode + DSP over a full track), and cached per design-v3 D6's cache-boundary split.
It is a pure function of the file's bytes plus this module's version — it does not
know about cue points, phrase grids, vocal zones as *interpreted* signals, or
`Track`. `ingestion/cue_derivation` (separate spec) consumes `RawFeatures` to build
`Track`.

**`Track` (design-v3 §5.1) field origin**, so every v1 field traces to exactly one
module:

| `Track` field | Source |
|---|---|
| `content_hash`, `duration`, `sample_rate` | **here** |
| `bpm`, `bpm_confidence`, `beat_times[]`, `downbeat_times[]`, `downbeat_confidence` | **here** |
| `key`, `key_confidence` | **here** — computed here, passed through unchanged |
| `lufs_integrated`, `true_peak`, `energy_curve[]` | **here** |
| `vocal_mask[]` | **here** — see §9 on the §4.2-table ambiguity this resolves |
| `grid_start`, `grid_confidence`, `free_intro_end`, `phrase_length_bars`, `phrase_grid[]`, `structure_template`, `cue_ins[]`, `cue_outs[]`, `status` | `cue_derivation` — cheap, metadata-only, derived from `RawFeatures` |
| `familiarity_score`, `era`, `is_club_edit` | `common/llm_service` (already specced) |
| `analysis_version` | composed from `feature_extractor_version` + `cue_derivation_version` |
| `id`, `path` | assigned by the ingestion orchestrator (not yet specced — out of scope here) |

**Out of scope for this spec** (all `cue_derivation`'s job, even though it consumes
this module's output): boundary/novelty detection, `phrase_grid[]`, `hook_exit` /
`hook_in`, interpreting `vocal_mask[]` into a cost term, cue emission, `status`
quarantine, `structure_template` classification. Also out of scope: SSM repetition
analysis and section labelling (both v2, design-v3 §6.3 Steps 2–3).

---

## 2. Data contract — `RawFeatures` (`schema.py`)

```
RawFeatures:
  content_hash             : str          # SHA-256 of raw file bytes (§5) — NOT of
                                           # decoded PCM; NOT the cache key by itself
  feature_extractor_version: str          # this module's version (§5); paired with
                                           # content_hash as the actual cache key (D6)
  source_path               : str         # informational only — never part of the
                                           # cache key (D6: renames must not re-analyse)
  duration                   : float       # seconds
  sample_rate                 : int         # canonical 48000 (D25)

  # tempo (§1.1) — float, never floored; beat_times[] is the thing to trust
  bpm                          : float
  bpm_confidence                : float     # see §6 — includes librosa cross-check
  beat_times                     : list[float]     # seconds

  # downbeats — see §6 for the v1 heuristic and its honest confidence ceiling
  downbeat_times                  : list[float]    # seconds
  downbeat_confidence               : float
  beats_per_bar                      : int          # hardcoded 4 in v1 (F8) — present
                                                      # on the contract now so a
                                                      # triple-meter track doesn't
                                                      # silently corrupt every
                                                      # downstream bar-index computation
                                                      # later (F8's explicit ask)

  # per-bar feature stack (§6.3 Step 1) — one entry per detected downbeat interval
  per_bar_features                    : list[PerBarFeatures]

  # loudness (§1.8, D23)
  lufs_integrated                       : float
  true_peak                              : float
  energy_curve                            : list[float]   # short-term LUFS per bar,
                                                            # aligned 1:1 with
                                                            # per_bar_features by index

  # vocal signal — raw only, see §9
  vocal_band_energy                        : list[float]  # 300Hz-3kHz energy per bar,
                                                            # aligned 1:1 with
                                                            # per_bar_features

  # harmony (§1.2, D10) — nullable soft score
  key                                        : str | None  # e.g. "8B" (Camelot)
  key_confidence                              : float | None

  # riser candidates (F4) — frame-level, not bar-gated (risers precede a usable grid)
  riser_candidates                             : list[RiserCandidate]

PerBarFeatures:
  bar_index         : int
  start_time         : float
  end_time            : float   # v2 — the true end of this bar (the next
                                  # downbeat), not reconstructed downstream.
                                  # Consumers must use this, not "the next
                                  # bar's start_time," for the last bar.
  rms                 : float
  spectral_centroid    : float
  spectral_flux          : float
  low_band_energy          : float
  high_band_energy          : float
  chroma_vector              : list[float]      # 12-dim

RiserCandidate:
  start_time      : float
  resolution_time  : float    # the terminating transient (F4)
  confidence        : float
```

All positions in seconds, `float64` (D20) — no sample indices anywhere in this
contract; sample-rate-aware conversion happens once, later, inside a renderer.

---

## 3. Canonical format & loading (`loader.py`)

**48kHz float32 stereo, pinned at ingestion (D25).** `load_canonical(path) ->
StereoPCM` always returns audio at this rate — never a file's native rate. This is
the only place in the module allowed to import an audio decoder.

**v2: corrected to match the installed Essentia build's actual API** (v1 assumed
`AudioLoader`/`MonoLoader` took a `sampleRate` parameter; neither does on this
build). The real technique: Essentia's `AudioLoader` loads at the file's native rate
while preserving its real channel count (it has no rate-conversion parameter at
all); `MonoLoader` *does* resample but also downmixes to mono, which would silently
discard genuine stereo content before "upcasting" it back — not what D25's
mono-upcast rule is for (that rule covers genuinely mono *sources*, not throwing
away stereo content this loader already has). So `load_canonical` loads via
`AudioLoader` at native rate, then resamples explicitly to 48kHz via Essentia's
`Resample` algorithm, run independently per channel. Mono sources (native channel
count 1) upcast to stereo by duplicating the single channel.

---

## 4. Tooling decision

Confirmed by an install spike on this machine (Python 3.11, macOS arm64) against a
real 268s Bollywood track:

| | Load time | BPM estimate |
|---|---|---|
| librosa (`audioread` backend) | 46.3s | 130.81 |
| Essentia (`MonoLoader` + `RhythmExtractor2013`, `method="multifeature"`) | 0.42s | 130.59, confidence 1.93 |

`MonoLoader` here is the spike's own benchmark choice — a quick load-speed comparison, not
the adopted production technique. `load_canonical` (§3, corrected in v2) uses
`AudioLoader` + a separate per-channel `Resample` pass instead, specifically because
`MonoLoader` downmixes to mono and would discard real stereo content. **Re-measured on
this same track**: `load_canonical` takes **~3.2s** (three runs: 3.39s, 3.28s, 3.19s) —
meaningfully slower than the `MonoLoader`-only figure above (the separate `Resample`
pass over both channels adds real cost the fused `MonoLoader` load+resample+downmix
didn't pay), so the "~100x faster than librosa" framing was wrong as originally
written. Still ~14x faster than librosa's 46.3s, not 100x — the tooling choice (Essentia
over librosa) still holds, just not by the margin first claimed.

**madmom is dropped.** Its C-extension build failed on this machine — blocked by an
unaccepted Xcode license (`sudo xcodebuild -license`), a local/environment issue, not
a real madmom/numpy incompatibility. Resolving that was rejected in favor of the
librosa-only downbeat fallback; see §6 for what that costs.

**Essentia is the primary engine** for load, rhythm, loudness, spectral features,
chroma, and key — confirmed via this build's actual API surface (`RhythmExtractor2013`,
`LoudnessEBUR128`, `TruePeakDetector`, `SpectralCentroidTime`, `Flux`, `NNLSChroma`,
`KeyExtractor` all present), and ~14x faster to load than librosa on the measured
track (re-measured for `load_canonical`'s actual `AudioLoader`+`Resample` path — see
the note above; the original ~100x figure was `MonoLoader`-only, not what's used in
production). **librosa is retained only as an independent cross-check** on `bpm`/
`beat_times` (§6) — not load-bearing for any field on its own — because design-v3 §11
explicitly treats disagreement between two independent trackers as a useful signal,
not noise to be resolved by picking one library and ignoring the other.

---

## 5. Content hash & caching (`content_hash.py`, `cache.py`)

**`content_hash` = SHA-256 of the raw file bytes, streamed, computed before any
decode.** Deliberately *not* a hash of decoded PCM: the entire point of caching on
content is to let a cache hit skip decode + DSP entirely (D6: "expensive... run
rarely"). If computing the key required decoding first, a "cache hit" would still pay
most of the cost it exists to avoid.

**Tradeoff, stated explicitly:** an ID3-tag-only edit changes the file's bytes and
therefore looks like a new file — one redundant re-extraction, never a correctness
issue. This is the right side of the tradeoff given D6's own justification ("renames
don't re-analyse and duplicates collapse") — both of those properties hold under a
raw-byte hash; tag-invariance was never the stated requirement.

**v3: concurrency-safe caching.** `ingestion/orchestrator` (spec in progress) is the
first module to ever call `get_or_extract_features` from multiple processes at once
— it dispatches per-track work across a process pool (`joblib`/`loky`). Two different
paths with identical audio content, submitted in the same batch, can both cache-miss
the same `(content_hash, extractor_version)` key at the same moment. Two fixes,
neither changing this function's signature:

**Fix 1 — atomic write.** `_write` no longer writes the final path directly. It
writes to a uniquely-named temp file in the same directory
(`{key}.json.tmp.{pid}.{uuid4().hex}` — the pid+random suffix matters; a single
fixed tmp name would just move the race one level down to two processes writing the
*same* tmp file), then atomically renames it onto the final path (`Path.replace()`,
`os.replace()` under the hood — atomic on both POSIX and Windows). This makes
cache-file corruption structurally impossible, regardless of how many processes race
on the same key.

**Fix 2 — cross-process claim, so concurrent callers coordinate instead of
duplicating expensive work.** Before extracting, a caller atomically tries to create
a `{key}.lock` sentinel file via `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`
— itself atomic, the same primitive real lockfile implementations use. Win the race
→ extract, write atomically (fix 1), then remove the lock in a `finally` (a normal
extraction exception still releases it, not just the success path). Lose the race →
another process is already extracting this exact content; wait for its cache file to
appear (polling every `_LOCK_POLL_INTERVAL_S`) instead of redoing the (expensive, D6)
work.

**Bounded wait, with self-healing reclaim — not an unbounded lock.** The wait is
capped at `_LOCK_WAIT_TIMEOUT_S` (300.0s — roughly 94x this module's own measured
~3.2s/track benchmark, §4: generous, but finite). This matters specifically because
of `orchestrator`'s own documented worker-crash risk: a lock file left behind by a
process that crashed mid-extraction (a native Essentia crash on malformed audio, not
a normal Python exception this module's own `try`/`except` could catch) must never
become a permanent hang for every future caller. On timeout, the waiting caller
doesn't just fall back to a one-off redundant extraction — it deletes the
presumably-stale lock and loops back to attempt its own claim. This is
**self-healing**: the first caller to notice a stale lock clears it for every caller
after it, not just for itself. A naive one-shot fallback (extract once, unclaimed,
leave the stale lock in place) would leave that lock behind forever, forcing every
subsequent caller for that key to independently wait out the same timeout, forever.

```
get_or_extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures
  content_hash = hash_file(path)                          # cheap, no decode
  key = (content_hash, config.extractor_version)
  loop until an overall deadline (_LOCK_WAIT_TIMEOUT_S from when this call started):
    hit           -> load cached RawFeatures (JSON), return — no decode
    claim wins    -> extract_features(path, config), write atomically (temp+rename),
                     release the claim (always, even on failure), return/raise
    claim loses   -> poll: wait for the cache file to appear, or for the claim
                     to disappear (the claimer gave up without writing) and retry
    past deadline -> treat the claim as stale, delete it, reset the deadline,
                     retry claiming (self-healing — not a one-shot fallback)

extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures
  # pure extraction, no cache lookup — always decodes and runs the full pipeline
```

Cache storage still mirrors `llm_service`'s pattern
(`resources/documentation/common/llm_service/spec.md` §9): disk-backed, one JSON
file per key, under `FeatureExtractorConfig.cache_dir` — **with the v3 caveat** that
a transient `{key}.lock` file can coexist alongside a key during extraction; it never
persists past a successful or failed claim (barring the crash case §5 already
designs around).

**No new config field.** `_LOCK_POLL_INTERVAL_S`/`_LOCK_WAIT_TIMEOUT_S` are private
module-level constants in `cache.py`, matching this module's existing pattern for
implementer-chosen algorithm constants (e.g. `rhythm.py`'s `_DOWNBEAT_WINDOW_S`) —
only genuinely per-user-tunable values live on `FeatureExtractorConfig`.

**No new dependency** — `os.open`/`O_EXCL`, `Path.replace`, `time` are all stdlib.

**`feature_extractor_version` is a hand-maintained constant** (`config.py`), bumped
whenever extraction logic changes (a new Essentia algorithm version, a changed
heuristic in §6/§7). It is not auto-derived from anything — the same manual-bump
pattern `llm_service` uses for `prompt_version`, and the same honesty caveat applies:
forgetting to bump it after a real algorithm change is a silent-staleness risk, not
one this module can detect on its own.

---

## 6. Rhythm — bpm, beat and downbeat detection (`rhythm.py`)

- `bpm`/`beat_times[]`: Essentia `RhythmExtractor2013(method="multifeature")` is
  primary. **`bpm` is stored as the raw float `RhythmExtractor2013` returns — never
  rounded or floored** (§1.1: flooring 128.4 to 128 drifts ~0.75s over four minutes).
- **librosa cross-check**: `librosa.beat.beat_track` runs independently on the same
  canonical PCM. `bpm_confidence` is Essentia's own `beats_confidence` output,
  discounted by a penalty scaled to `|essentia_bpm - librosa_bpm|` — two independent
  trackers agreeing tightens confidence; disagreement loosens it. This is the one
  piece of design-v3 §11's "disagreement is a data point" philosophy this module
  implements directly.
- **Downbeat phase — the real v1 gap left by dropping madmom.** Essentia has no DBN
  downbeat tracker equivalent. v1 heuristic, assuming 4/4 (`beats_per_bar = 4`, F8):
  for each of the 4 candidate phase offsets into `beat_times[]`, compute mean
  low-band energy (bass/kick, §1.7) at beats landing on that phase; pick the phase
  maximizing contrast against the other three; `downbeat_confidence` is the
  normalized margin between the best and second-best phase. **This is honestly
  weaker than the design doc's original madmom-based assumption** — design-v3 §8
  already flags downbeat phase as unsolved on film music even *with* madmom
  ("Beat tracking is largely solved; downbeat phase is not"). This module's job is to
  emit that weakness as a low, honest `downbeat_confidence`, not to solve it —
  `cue_derivation`'s D7 quarantine is what acts on a low score.

---

## 7. Per-bar feature stack (`spectral_features.py`)

Design-v3 §6.3 Step 1's exact six fields, computed per bar once `downbeat_times[]`
exists: `rms`, `spectral_centroid` (Essentia `SpectralCentroidTime`), `spectral_flux`
(Essentia `Flux`), `low_band_energy`/`high_band_energy` (band split per §1.7),
`chroma_vector` (Essentia `NNLSChroma`, 12-dim). One array, computed once, cached —
`cue_derivation` reads it for three purposes (D8's novelty curve, D27's `hook_exit`,
boundary proposals) without recomputing anything or touching audio (§6.3: "one
component, three consumers").

---

## 8. Loudness (`loudness.py`)

Essentia's `LoudnessEBUR128` gives `integratedLoudness` directly (→
`lufs_integrated`) and a `momentaryLoudness` series (400ms windows). `true_peak` via
Essentia's `TruePeakDetector`.

**`energy_curve[]` is *not* `LoudnessEBUR128`'s `shortTermLoudness` output taken
as-is** — its fixed 3-second window doesn't align to bar boundaries at most tempos.
`energy_curve[]` is built by averaging the `momentaryLoudness` series within each
bar's own `[start_time, end_time)` window (v2: `end_time` is a `PerBarFeatures` field,
§2 — not reconstructed from the next bar's `start_time`), giving one LUFS value per
bar, aligned 1:1 with `per_bar_features` — matching D23's "short-term LUFS per bar"
exactly, and reusing "the loudness machinery from §1.8" as instructed rather than
recomputing RMS (D23: RMS under-weights the low end this repertoire's felt energy
depends on).

---

## 9. Vocal band energy — raw signal only (`vocal_band.py`)

`vocal_band_energy[]`: per-bar energy in the 300Hz–3kHz band (D22's proxy), one value
per bar, aligned with `per_bar_features`.

**This resolves an apparent tension in design-v3, worth stating explicitly.** §4.2's
"where things live" table lists "Vocal mask | Cue derivation (D22)", but §4 also
states cue derivation is metadata-only and never touches audio — and a 300Hz–3kHz
band-energy measurement requires PCM. Read together, §4.2's placement is about where
`vocal_mask[]`'s *cost-formula interpretation* (D22's `junction_cost += w_vocal · ...`
term) happens, not where the DSP runs. **Resolution used here:** this module computes
the raw per-bar band energy and it becomes `Track.vocal_mask[]` unchanged —
`cue_derivation` and the (out-of-spec) edge builder read it, they don't recompute or
transform it. No interpretation (thresholding, penalty weighting) happens in this
module.

---

## 10. Key estimation (`key_estimation.py`)

Essentia `KeyExtractor` → `key` (Camelot notation, §1.2), `key_confidence`. Nullable
soft score (D10) — never a hard gate anywhere downstream; this module's only job is
to report the estimate and its own confidence honestly, same posture as §6's
downbeat confidence.

---

## 11. Riser detection (`riser_detection.py`)

F4: "monotonic upward drift in spectral centroid terminating in a transient... cheap:
no segmentation model." Runs on a finer-grained frame-level spectral centroid series
(not bar-gated — risers occur in the free-time region before a reliable beat grid
exists, per F3). Detection: a sustained monotonic increase in frame-level spectral
centroid, ending at a detected onset transient. Output is a **candidate list**, not a
cue — `cue_derivation` decides whether to actually emit `riser_start` (D9's
exception).

---

## 12. Orchestration & config (`extract.py`, `config.py`)

```
FeatureExtractorConfig:
  extractor_version : str     # bumped by hand (§5)
  cache_dir          : str
  sample_rate        : int    # 48000, but explicit rather than hardcoded (D25)

extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures
  1. load_canonical(path)                          # §3
  2. rhythm = detect_rhythm(pcm)                     # §6
  3. per_bar = compute_per_bar_features(pcm, rhythm)   # §7
  4. loudness = compute_loudness(pcm, per_bar)           # §8
  5. vocal = compute_vocal_band_energy(pcm, per_bar)       # §9
  6. key = estimate_key(pcm)                                # §10
  7. risers = detect_risers(pcm)                              # §11
  8. assemble RawFeatures from the above + duration/sample_rate
```

`extract_features` never checks or writes the cache — that's `cache.py`'s
`get_or_extract_features` (§5), the only entry point real callers use.

---

## 13. Testing strategy

- **Unit tests use small synthetic fixtures** (a generated click track + tone at a
  known BPM, built in-process with numpy in `conftest.py`) — deterministic, no
  external file dependency, fast. This is what most of the test suite runs against.
- **`music/` is gitignored** (repo `.gitignore`: `# testing tracks` / `/music`) — real
  Bollywood tracks live there locally but aren't part of the repo. A separate
  `test_real_audio_smoke.py` is `pytest.mark.skipif`-guarded on the fixture file's
  existence, so the default suite passes on a fresh clone with no `music/` directory,
  but running it locally sanity-checks real output (the spike's own numbers — BPM
  ~130.6–130.8, load time — are the reference values to assert loosely against, e.g.
  BPM within ±2 of the known reference, not exact equality against a moving target).
- `schema.py` has no dedicated test file — plain data classes carry no behavior.
- Every other module in §13's file layout gets its own test file, isolated: rhythm
  cross-check logic, per-bar feature computation, loudness windowing (§8's
  momentary→per-bar averaging is the one non-trivial piece of logic worth a direct
  test), **content-hash/cache round-trip (hit vs. miss, version-bump invalidation,
  and — v3 — concurrent-access coordination: two racing callers for the same key
  extract exactly once, a failed extraction releases its claim so a waiter retries
  immediately rather than hanging, an orphaned lock is reclaimed after
  `_LOCK_WAIT_TIMEOUT_S`, and no `.tmp.*` file survives a successful write)**,
  riser detection on a synthetic monotonic-centroid-drift fixture.

---

## 14. File layout

```
src/ingestion/feature_extractor/
  __init__.py             # public exports: RawFeatures, PerBarFeatures,
                           # RiserCandidate, FeatureExtractorConfig,
                           # extract_features, get_or_extract_features
  schema.py                # RawFeatures, PerBarFeatures, RiserCandidate (§2)
  config.py                 # FeatureExtractorConfig, EXTRACTOR_VERSION (§5, §12)
  loader.py                  # load_canonical() — 48kHz float32 stereo decode (§3)
  content_hash.py              # hash_file() — SHA-256 of raw bytes (§5)
  cache.py                       # get_or_extract_features() — cache read/write,
                                  # atomic write + cross-process claim (§5, v3)
  rhythm.py                        # detect_rhythm() — bpm/beat_times/downbeats (§6)
  spectral_features.py               # compute_per_bar_features() (§7)
  loudness.py                          # compute_loudness() — LUFS/true_peak/energy_curve (§8)
  vocal_band.py                          # compute_vocal_band_energy() (§9)
  key_estimation.py                        # estimate_key() (§10)
  riser_detection.py                         # detect_risers() (§11)
  extract.py                                   # extract_features() orchestrator (§12)

tests/ingestion/feature_extractor/
  conftest.py                # synthetic click-track/tone fixture generator;
                              # real-audio fixture path (skipped if music/ absent)
  test_schema.py              # (only if any validation logic beyond field types exists)
  test_loader.py
  test_content_hash.py
  test_cache.py                # hit/miss/version-bump invalidation, plus v3's
                                # concurrent-access/atomicity/stale-lock coverage (§13)
  test_rhythm.py                 # includes the librosa cross-check confidence logic
  test_spectral_features.py
  test_loudness.py                 # momentary -> per-bar averaging (§8)
  test_vocal_band.py
  test_key_estimation.py
  test_riser_detection.py
  test_extract.py                    # orchestration, assembled RawFeatures shape
  test_real_audio_smoke.py             # skipif no music/ fixture — real-track sanity check
```

---

## 15. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| madmom for beat/downbeat tracking | Essentia `RhythmExtractor2013` + librosa cross-check; heuristic downbeat phase (§6) | Build blocked by this machine's unaccepted Xcode license; user chose the librosa-only fallback over resolving a local system dependency |
| `content_hash` over decoded PCM | `content_hash` over raw file bytes, pre-decode (§5) | A cache hit must skip decode entirely — hashing decoded audio would pay most of the cost caching exists to avoid |
| `energy_curve[]` = `LoudnessEBUR128.shortTermLoudness` directly | Per-bar average of `momentaryLoudness` (§8) | The built-in short-term window (3s, fixed) doesn't align to bar boundaries at most tempos |
| Vocal-mask thresholding/interpretation done here | Raw `vocal_band_energy[]` only; interpretation deferred to `cue_derivation` (§9) | Keeps this module's job "compute signal," not "decide what it means" — the D22 cost formula is a planning-adjacent concern |
| Real Bollywood tracks (`music/`) as committed test fixtures | Synthetic in-process fixtures for the default suite; `music/` used only by a skip-guarded smoke test (§13) | `music/` is gitignored; the default suite must pass on a fresh clone with no local audio files present |
| A shared in-memory coordination structure (e.g. a `multiprocessing.Manager` dict) for cache concurrency (v3, §5) | A file-system-based claim (`.lock` sentinel via `O_CREAT\|O_EXCL`) | A plain in-memory structure in one process is invisible to the separate OS processes `orchestrator`'s process-pool backend dispatches work to — the filesystem is the only thing every worker process actually shares |

---

## 16. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | **Answered 2026-08-24 — yes, it quarantines far too many, and the root cause is more specific than this question assumed.** Measured on the real 69-track corpus: **52 `cut_only`, 7 `excluded`, 10 `ok`** — D7 fires on 86% of the library. `downbeat_confidence` median is `0.053` against a `cut_only_threshold` of `0.15`. See `## Amendments` for the diagnosis, the tested replacement, and what it does *not* fix | **Unblocked but not yet fixed.** The tier ladder cannot reach tier 2 on this library (`processing/edge_builder` spec §12 Q10: tier 2 eligible on 12 of 3,782 pairs, winning 0). A fix is a §6 change plus an `extractor_version` bump |
| Q2 | Is a single `bpm_confidence` penalty term (Essentia vs. librosa delta) enough signal, or does `cue_derivation`/D7 need the two raw estimates separately to reason about disagreement itself? | `RawFeatures.bpm_confidence` shape — currently a single scalar (§2, §6) |
| Q3 | JSON cache file size at scale — `per_bar_features[]` with a 12-dim `chroma_vector` per bar could run to a few hundred KB per track for a long film song; worth confirming this doesn't become a real cost at a few hundred tracks | Cache storage format (§5) — currently assumed fine, unverified at scale |
| Q4 | `_LOCK_WAIT_TIMEOUT_S` (300s, §5, v3) is a round, defensible default, not empirically tuned — is it right for much larger files than the ~268s benchmark track, where extraction could plausibly take meaningfully longer than "a few seconds"? | §5's timeout constant — currently assumed generous enough, unverified against large-file extraction times |
| Q5 | **Half-bar downbeat ambiguity is unresolved and, as of the 2026-08-24 investigation, unmeasured.** §6 picks the bar phase by low-band energy, but in 4/4 material beats 1 and 3 *both* carry kick — so the heuristic reliably finds the two-beat kick grid and then chooses between the two candidates near-arbitrarily. A consistently half-bar-shifted grid puts every "downbeat" on beat 3. Nothing in the pipeline currently detects or reports this | Tier 2's musicality specifically — a bass swap at "bar 8 of a 16-bar phrase" lands two beats out if the grid is shifted. Also any bar-aligned cut. Was masked by Q1's over-quarantining: while 86% of tracks were quarantined, the phase never had to be right |

---

## Amendments

- **2026-08-24** — **Q1 answered; §6's `downbeat_confidence` diagnosed as mis-scaled.
  No behaviour changed in this pass** — recorded so the analysis is not repeated, and
  deliberately left unfixed pending a decision on §6's replacement metric.

  **How it surfaced.** Verifying `Junction.bar_seconds` on the real corpus for
  `processing/edge_builder` v2, which showed tier 2 winning **0 of 3,477 edges**
  (that spec §12 Q10). Tracing that back: 52 of 69 tracks are `cut_only`, and §5's
  tier-2 rule drops the tier whenever either side is quarantined.

  1. **Root cause — the metric conflates two different failures.** §6 computes
     `downbeat_confidence = (best_score − second_score) / best_score`, the margin
     between the winning bar phase and the runner-up by low-band (20–150 Hz) energy.
     In 4/4 music **beats 1 and 3 both carry kick**, so the top two phases are
     routinely near-identical (top-2 phases sat 2 beats apart on 12 of 20 sampled
     tracks). Measured per-phase energies:

     | Track | Per-phase low-band energy | Confidence |
     |---|---|---|
     | Chhote Chhote Peg | `[168.4, 205.2, 157.8, 206.7]` | `0.007` |
     | Disco Disco | `[46.6, 178.9, 58.9, 189.0]` | `0.054` |
     | Desi Girl | `[69.1, 65.9, 66.6, 67.1]` | `0.029` |

     The first two have **unmistakable** bar structure — kicks 3× the other beats —
     and score *lower* than the third, which has no discernible structure at all. The
     formula reports "the winner barely beat the runner-up," which for tight
     programmed drums is the signature of a **good** grid, not a bad one. Corpus-wide
     the metric is crushed toward zero: median `0.053`, max `0.644`, only one track
     above `0.5`. Same class of defect as the `phrase.strength` finding recorded in
     `processing/edge_builder` spec v1's amendments — a raw score read as a `[0,1]`
     confidence.

  2. **Tested replacement — "pair contrast."** The discriminating comparison is not
     best-vs-second but **the two kick phases against the two non-kick phases**:
     `(mean(top two) − mean(bottom two)) / mean(top two)`. Validated across all 69
     tracks:

     | | current | pair contrast |
     |---|---|---|
     | median | `0.053` | `0.168` |
     | max | `0.644` | `0.817` |
     | ≥ 0.15 | 13 tracks | **37 tracks** |

     It discriminates rather than merely inflating: the eight worst tracks by pair
     contrast (`Desi Girl` `0.027`, `Halka Halka` `0.031`, `Ding Dong` `0.045`) stay
     well below any plausible threshold. **Caveat:** its floor is `0.027`, above
     `cue_derivation`'s `exclude_threshold` of `0.01`, so *no* track would ever be
     excluded — both thresholds are calibrated to the current metric's scale and
     would need retuning alongside any swap. **Second caveat:** it assumes 4/4 with
     kicks on 1 and 3 (F8's assumption), and would misread four-on-the-floor.

  3. **Negative results, recorded so they are not retried.** Multi-band analysis was
     tested as a way to separate the two kick phases. Median separation between them:
     **low 7.1%** (the current feature), **mid 3.3%**, **high 4.2%**, **bass-range
     chroma change 8.9%**. Mid and high are *worse* than low. Bass-range chroma change
     (chord-root change, the expected downbeat cue) edges ahead on median but is
     wildly inconsistent — 27–32% on two tracks, 1.3% on another. Full-spectrum chroma
     change was also tried and is pure noise (four phases within 4%: `[0.342, 0.329,
     0.340, 0.333]`). **No single band reliably identifies the true downbeat.** That
     different tracks are separated by different bands is the signature of a problem
     wanting a learned, temporally-smoothed model — i.e. the madmom DBN tracker §6
     already names as the dropped v1 dependency — rather than another hand-picked band
     and threshold.

  4. **New Q5** records the half-bar ambiguity that (2) does *not* fix and (3) failed
     to fix. Pair contrast measures whether a reliable two-beat kick grid exists; it
     says nothing about which of the two kicks is beat 1. Over-quarantining had been
     masking this — while 86% of tracks were quarantined, the phase never had to be
     right.
