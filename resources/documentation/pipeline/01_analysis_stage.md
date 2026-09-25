# Analysis Stage

Part of [resources/documentation/pipeline/](00_pipeline_map.md). Covers the expensive,
per-track, cached half of the pipeline (design-v3 **D6**) — everything that runs once per
track and produces the fields on `Track` that Planning and Render consume.

Precise field lists, formulas, and defaults live in each module's own `spec.md`, linked
below. This file gives the mental model, not the contract.

---

## 0. Stage boundary

Only `ingestion/feature_extractor` is allowed to touch raw PCM (its own spec's invariant,
§0). Everything downstream of it — `cue_derivation`, `orchestrator`, and everything in
Planning/Render — consumes only the metadata it produces (design-v3 **D2**, one layer
earlier than Planning's own metadata-only invariant). `acquisition/youtube_downloader`
sits upstream of all of this, turning URLs into local files; it has no dependency on
`ingestion/` and vice versa.

---

## 1. Stage map

```
YouTube URLs (optional)
    │
    ▼  acquisition/youtube_downloader
local audio files
    │
    ▼  ingestion/feature_extractor        (the only module that decodes/DSPs audio)
RawFeatures   (cached: content_hash, feature_extractor_version)
    │
    ▼  ingestion/cue_derivation           (pure function of RawFeatures, no audio, no cache)
CueDerivationResult
    │
    ▼  ingestion/orchestrator             (concurrency + assembly, no DSP of its own)
Track
```

---

## 2. Caching model

Cache key is `(content_hash, feature_extractor_version)` — **never filename** (design-v3
**D6**). `content_hash` is a SHA-256 of the raw file bytes, computed *before* any decode,
so a cache hit skips decode+DSP entirely. `feature_extractor_version` is a hand-maintained
constant, bumped manually whenever the extraction logic changes — swapping a beat tracker
or a chroma implementation must invalidate stale cached results automatically, which is
exactly what keying on this pair (rather than, say, just the hash) guarantees.

`cue_derivation` deliberately has **no cache of its own** — it's the cheap, volatile half
of the same D6 split, meant to be re-run on every tuning change without re-paying
`feature_extractor`'s cost.

[04_transcription.md](04_transcription.md) proposes a **new cache-key axis**
(`transcription_version`) alongside `feature_extractor_version`, for the same reason:
swapping the ASR model must invalidate stale transcripts the same way swapping the beat
tracker already invalidates stale features.

---

## 3. `acquisition/youtube_downloader`

Turns a list of YouTube URLs into local MP3s: `download_tracks(urls, config,
on_progress) -> DownloadResult`, mirroring `IngestionResult`'s `tracks[]`/`failures[]`
shape. Runs **sequentially**, not concurrently (avoids YouTube throttling — unlike
`orchestrator`'s CPU-bound worker pool), and is idempotent across runs via a persistent
manifest keyed on `video_id`. Deliberately never expands playlists automatically or
propagates provenance (source URL, run ID) into `Track` — wiring the two layers together
is left to a future top-level pipeline entry point.

Full detail: [spec](../acquisition/youtube_downloader/spec.md).

---

## 4. `ingestion/feature_extractor`

The only module that decodes audio or runs DSP. Loads to the canonical format (48kHz
float32 stereo, design-v3 **D25**) and produces `RawFeatures`: BPM + confidence,
beat/downbeat times, a per-bar feature stack (`rms`, `spectral_centroid`, `spectral_flux`,
low/high band energy, 12-dim `chroma_vector`), LUFS + true peak, a per-bar `energy_curve`,
`vocal_band_energy` (300Hz–3kHz), Camelot `key` + confidence (nullable), and riser
candidates. Built on Essentia (librosa only as a BPM cross-check; madmom was dropped —
a local build blocker, not a real incompatibility).

**Known defect (open thread T1, see `overview.md`):** `downbeat_confidence` is
mis-scaled — it reads near-zero exactly when a track's drum programming is *tightest*,
because beats 1 and 3 both carry kick in common 4/4 Bollywood production, making the two
candidate downbeat phases look nearly identical. On a real 69-track corpus this
quarantines 86% of the library and makes tier-2 transitions (see
[02_planning_stage.md](02_planning_stage.md)) almost unreachable. A replacement metric
("pair contrast") is diagnosed and measured but not yet decided on — this is a pending
decision, not unfinished code.

Full detail: [spec](../ingestion/feature_extractor/spec.md).

---

## 5. `ingestion/cue_derivation`

A pure function of `RawFeatures` — never touches audio, milliseconds, safe to re-run on
every tuning change. Produces the rest of `Track`: `grid_start`/`grid_confidence` (anchored
on the first *detected* downbeat, not file start), `phrase_grid[]` (a Foote-checkerboard
novelty curve over six per-bar fields including `chroma_vector` — detects boundary
*locations* only, no repetition analysis), `structure_template` (`"edm"`/`"film"`/`"unknown"`,
a two-signal heuristic used to condition transition-tier penalties downstream),
`hook_in`/`hook_exit` (a percentile-threshold energy+vocal "plateau" proxy for "the
chorus"), ranked `cue_ins[]`/`cue_outs[]`, and the `status` quarantine gate (`ok` /
`cut_only` / `excluded`, driven by `grid_confidence` alone — key confidence never gates
anything, per design-v3 **D10**).

**Known gap (open thread T8, see `overview.md`):** `hook_in`/`hook_exit` is explicitly an
energy+vocal-density *proxy* for "the chorus," not true repetition-based structure
detection. The module's own spec has listed "SSM repetition analysis and full section
labelling" as out of scope since it was first written, deferred to a "v2" that was never
built. [05_song_structure.md](05_song_structure.md) proposes that v2.

Full detail: [spec](../ingestion/cue_derivation/spec.md).

---

## 6. `ingestion/orchestrator`

Glues `RawFeatures` + `CueDerivationResult` into `Track`, and is the first module with
real concurrency needs — dispatches per-track work across a process pool
(`joblib`/`loky`, chosen over stdlib `ProcessPoolExecutor` because a single worker crash
poisons the whole pool under stdlib; `loky` detects and respawns). One bad track never
crashes the batch — a failing track becomes an `IngestionFailure`, not an exception that
aborts everything else (the same spirit as D7's quarantine philosophy, one level up).

Full detail: [spec](../ingestion/orchestrator/spec.md).

---

## 7. Where the new modules slot in

Both proposed additions are Analysis-stage work — expensive, per-track, cached, and never
touched again once computed:

- [04_transcription.md](04_transcription.md) — a new sibling module alongside
  `feature_extractor`, running local ASR once per track.
- [05_song_structure.md](05_song_structure.md) — a `cue_derivation` v2 bump (the
  self-similarity segmentation half) plus a new sibling module (the labeling half, the
  only place a model call happens for this feature).
