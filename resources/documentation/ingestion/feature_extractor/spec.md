# Feature Extractor — Spec

**v2** — supersedes v1, see `archive/spec-v1.md`.

**What changed in v2** (both found during code review, before the module's first
merge — see `plan.md`): (1) `PerBarFeatures` gains `end_time` — v1 only stored
`start_time`, which forced `loudness.py`/`vocal_band.py` to each independently guess
a bar's end as "the next bar's start, or the literal end of the audio file for the
last bar." That guess was wrong for every track's last bar (the real end is the last
detected downbeat, not the file's end), silently widening the last bar's
`energy_curve`/`vocal_band_energy` window into any trailing outro/silence. Each bar
now carries its own true `end_time`, computed once where it's already known
(`spectral_features.py`), removing the guess entirely. (2) §3 corrected — it
described `AudioLoader` taking a `sampleRate` parameter, which doesn't exist on the
installed Essentia build; the real technique (load at native rate, then a separate
`Resample` pass) was implemented correctly and documented in code, but the spec text
itself was never brought back in line. Fixed here. Neither change affects the
public function signatures (`load_canonical`, `extract_features`,
`get_or_extract_features` are all unchanged) — only `PerBarFeatures`'s schema and
§3's description.

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

```
get_or_extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures
  1. content_hash = hash_file(path)                     # cheap, no decode
  2. key = (content_hash, config.extractor_version)
  3. hit  -> load cached RawFeatures (JSON, one file per key), return — no decode
     miss -> extract_features(path, config), persist under key, return

extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures
  # pure extraction, no cache lookup — always decodes and runs the full pipeline
```

Cache storage mirrors `llm_service`'s pattern (`resources/documentation/common/llm_service/spec.md`
§9): disk-backed, one JSON file per key, under `FeatureExtractorConfig.cache_dir`.

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
  test), content-hash/cache round-trip (hit vs. miss, version-bump invalidation),
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
  cache.py                       # get_or_extract_features() — cache read/write (§5)
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
  test_cache.py                # hit/miss/version-bump invalidation
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

---

## 16. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Does the phase-contrast downbeat heuristic (§6) hold up against `cue_derivation`'s D9 grid-origin logic in practice, or does its honestly-lower confidence quarantine too many tracks via D7? | Whether v1's downbeat approach is viable without revisiting the madmom/Xcode-license blocker |
| Q2 | Is a single `bpm_confidence` penalty term (Essentia vs. librosa delta) enough signal, or does `cue_derivation`/D7 need the two raw estimates separately to reason about disagreement itself? | `RawFeatures.bpm_confidence` shape — currently a single scalar (§2, §6) |
| Q3 | JSON cache file size at scale — `per_bar_features[]` with a 12-dim `chroma_vector` per bar could run to a few hundred KB per track for a long film song; worth confirming this doesn't become a real cost at a few hundred tracks | Cache storage format (§5) — currently assumed fine, unverified at scale |
