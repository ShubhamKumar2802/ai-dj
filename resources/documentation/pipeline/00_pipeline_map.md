# Pipeline Map

Entry point for `resources/documentation/pipeline/` — read this file first.

---

## 0. How to read this folder

This folder is a **narrative layer**, not a second contract layer. It exists so someone
can get the complete mental model of the AI DJ pipeline — what's built, what isn't, and
why the two new pieces (transcription, song structure) are designed the way they are —
without opening nine separate `spec.md` files first.

It does **not** replace anything:

- **`resources/documentation/<layer>/<module>/spec.md`** (per `resources/documentation/README.md`)
  stays the sole authoritative source for exact field lists, formulas, and defaults. When
  a pipeline file and a module spec would say the same fact, the pipeline file states it
  once, loosely, and links to the spec for the precise version. If they ever disagree,
  the module spec is right.
- **`resources/documentation/overview.md`** stays the terse, frequently-updated status
  tracker (the W1–W7 working order, the build-order coverage table, the T1–T8 open-threads
  table). Pipeline files link into that table by ID (`T1`, `T8`, ...) instead of restating
  status — `overview.md` is updated every time a task lands; these files are updated only
  when the pipeline's *shape* changes.
- **`resources/ai-dj-design-v3.md`** stays the actual design-rationale source of truth
  (D1–D27, the numbered decisions every module spec cites). CLAUDE.md previously pointed
  at a superseded early draft, `resources/ai-dj-domain-and-architecture.md`; that pointer
  has been corrected as part of writing this folder. Every `D#` citation below refers to
  `ai-dj-design-v3.md`.

---

## 1. The three-stage split, and why it's cost not concept

The pipeline is **Analysis → Planning → Render**, and the split is drawn by *iteration
cost*, not by subject matter (design-v3 **D6**):

| Stage | Touches audio? | Cost | Cached? | Re-run frequency |
|---|---|---|---|---|
| **Analysis** | Yes | Expensive (decode + DSP, or a model call) | Yes — `(content_hash, feature_extractor_version)` | Once per track, ever (until a tuning change bumps the version) |
| **Planning** | No — metadata only | Milliseconds | No — cheap enough to not need it | Constantly, every time weights/tiers are tuned |
| **Render** | Yes (reads PCM, writes PCM) | Deterministic execution | No | Once per finished `MixPlan` |

This is why `cue_derivation` (boundary detection, phrase grid, cue emission) is a
*separate* module from `feature_extractor` even though both are conceptually "analysis" —
`cue_derivation` is the cheap, volatile half of D6's split, expected to be re-tuned
constantly without re-paying decode+DSP cost, while `feature_extractor` is the expensive,
stable half. The same logic is why **Planning must never call a model** (design-v3 **D14**,
"no model in the planner") — a model call is Analysis-stage cost, and letting one leak into
Planning would break the "milliseconds, run constantly" property the whole stage depends on.

---

## 2. Stage map

| Stage | Module | Status | Spec | Pipeline doc |
|---|---|---|---|---|
| Analysis | `acquisition/youtube_downloader` | Done | [spec](../acquisition/youtube_downloader/spec.md) | [01](01_analysis_stage.md) |
| Analysis | `ingestion/feature_extractor` | Done (v3) — known defect T1 | [spec](../ingestion/feature_extractor/spec.md) | [01](01_analysis_stage.md) |
| Analysis | `ingestion/cue_derivation` | Done — hook detection is a proxy, not real structure (T8) | [spec](../ingestion/cue_derivation/spec.md) | [01](01_analysis_stage.md) |
| Analysis | `ingestion/orchestrator` | Done | [spec](../ingestion/orchestrator/spec.md) | [01](01_analysis_stage.md) |
| Analysis | `ingestion/transcription` — **new, proposed** | Not built | — | [04](04_transcription.md) |
| Analysis | `cue_derivation` v2 (SSM segmentation) — **new, proposed** | Not built | — | [05](05_song_structure.md) |
| Analysis | `ingestion/structure_labeler` — **new, proposed** | Not built | — | [05](05_song_structure.md) |
| Planning | `processing/edge_builder` | Done (v2) | [spec](../processing/edge_builder/spec.md) | [02](02_planning_stage.md) |
| Planning | `processing/path_search` | Done (W1) | [spec](../processing/path_search/spec.md) | [02](02_planning_stage.md) |
| Planning | `ingestion/familiarity_scorer` | Not built (W7) — inert `ν` term until then | — | [02](02_planning_stage.md) |
| Render | `render/transition_renderer` | Done — tier 3 only; 2/4/5 unimplemented | [spec](../render/transition_renderer/spec.md) | [03](03_render_stage.md) |
| Render | `render/playlist_renderer` | Done (Milestone B) | [spec](../render/playlist_renderer/spec.md) | [03](03_render_stage.md) |
| — | `experiments/llm_camelot_sequencer` | Sandbox, not production, no spec planned | — | [06](06_experiments_sandbox.md) |
| — | `experiments/whisper_bakeoff` — gates `ingestion/transcription` | Sandbox, draft spec, not built | [spec](../experiments/whisper_bakeoff/spec.md) | [04](04_transcription.md), [06](06_experiments_sandbox.md) |
| — | `experiments/lyrics_sourcing` — single-track pipeline: fetch synced lyrics (Whisper validates/falls back) + metadata → TOON timeline → local LLM structure labels | Sandbox, draft spec, not built | [spec](../experiments/lyrics_sourcing/spec.md) | [04](04_transcription.md), [06](06_experiments_sandbox.md) |

---

## 3. Data flow

```
audio files
    │
    ▼  acquisition/youtube_downloader (optional upstream)
local audio files
    │
    ▼  ingestion/{feature_extractor, cue_derivation, orchestrator}
Track[]                          ◄── proposed: + transcription, + real section structure
    │
    ▼  processing/edge_builder
ScoredEdges  (argmin junction plan per viable pair, every tier scored, cheapest wins)
    │
    ▼  processing/path_search
MixPlan  (beam search over K-of-N subset+order — the orienteering problem, not Dijkstra,
          not a BPM sort)
    │
    ▼  render/{transition_renderer, playlist_renderer}
one continuous WAV
```

Every arrow after `Track[]` is metadata-only until the final render step. This is what
makes Planning testable from small JSON fixtures with no audio (**D2**) — a property that
must hold for anything new added to this pipeline too, including the two proposed modules'
*outputs* (their raw model calls happen upstream, in Analysis; by the time anything
downstream reads `sections[]`/`transition_points[]`, it's just JSON like everything else
on `Track`).

---

## 4. What's new vs. what's built

The short version, elaborated in [04](04_transcription.md) and [05](05_song_structure.md):

- **Transcription** (timestamped lyrics via local ASR) — doesn't exist anywhere in this
  repo today, experimental or production. Proposed because repeated lyric lines are a
  cheap, strong signal for "this is the chorus/hook" that nothing currently captures.
- **Real song structure** (intro/verse/chorus/breakdown/outro, not just two proxy cue
  kinds) — explicitly deferred as "v2" in `cue_derivation`'s own spec since it was
  written, and logged as open thread **T8**: today's `hook_in`/`hook_exit` is an
  energy+vocal-density *proxy* for "the chorus," not real repetition-based detection.
  Everything needed for the real fix (`chroma_vector`) is already computed and cached by
  `feature_extractor` — nobody has written the self-similarity pass over it yet.

Neither proposal touches Planning or Render. Both are Analysis-stage additions that
produce more/better fields on `Track`, consumed the same way `bpm` or `key` already are.

---

## 5. Repo state caveat

Stated once, here, so it isn't repeated in every other file: as of this writing, the
working tree contains real, working content that git `HEAD` does not yet contain —
notably the entire `render/` layer (both renderers, Milestone A and B), `cue_derivation`'s
T7 fix (the `hook_exit` multi-candidate change), and all of `experiments/
llm_camelot_sequencer/`. A fresh clone of `HEAD` alone would only get as far as
`processing/path_search` (build-order step 5). Every "Done" status in this folder
describes the working tree, matching `overview.md`'s own current (uncommitted) content —
not necessarily what a clean checkout of the last commit would show. This is a fact about
repo hygiene, not a defect in the pipeline design; per this project's git workflow rule,
staging and committing is the user's action to take, not something these docs assume has
happened.

---

## 6. Where to look next

- Already-built stages, one file each: [01_analysis_stage.md](01_analysis_stage.md),
  [02_planning_stage.md](02_planning_stage.md), [03_render_stage.md](03_render_stage.md).
- The two proposed new modules: [04_transcription.md](04_transcription.md),
  [05_song_structure.md](05_song_structure.md).
- The sandboxed experiment that informed several of the decisions above:
  [06_experiments_sandbox.md](06_experiments_sandbox.md).
- The experiment that decides whether transcription gets built at all:
  [`experiments/whisper_bakeoff` spec](../experiments/whisper_bakeoff/spec.md).
