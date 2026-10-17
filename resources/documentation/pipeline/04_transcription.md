# Transcription — Pre-Spec Design Proposal

Part of [resources/documentation/pipeline/](00_pipeline_map.md). **Status: not built.**
This file is a pre-spec design proposal — detailed enough to promote into a real
`resources/documentation/ingestion/transcription/spec.md` via the `write-spec` skill, but
not yet approved/implemented as one. Until that promotion happens, this file is the
authoritative detail on the proposal; afterward, it shrinks to a summary-and-link like
[01_analysis_stage.md](01_analysis_stage.md).

---

## 0. Why this module

Nothing in this pipeline currently reads lyrics. The one concrete, well-supported reason
to add transcription: **a repeated lyric line is a strong, cheap signal that a section is
the chorus/hook** — independent of, and complementary to, the energy/vocal-density
heuristic `cue_derivation`'s `hook_in`/`hook_exit` already uses. This is the module's
entire justification; it is not proposed as a general "understand the song" capability.

---

## 1. Non-goals

**This module does not produce section boundaries or timestamps for structure.** LLMs and
ASR models are unreliable at inventing precise numeric boundaries from a text/summary
description — this isn't a hypothesis, it's already visible in this repo:
[06_experiments_sandbox.md](06_experiments_sandbox.md)'s `structure_llm.py` experiment
needs a whole separate clamp-and-reject validation function just to sanity-check **four**
LLM-guessed numbers (`intro_end`, `chorus1_start`, `chorus1_end`, `outro_start`) against
the track they describe. Transcription's timestamps come directly from the ASR model's own
forced-alignment output (a mechanical property of the audio, not a generated guess), which
is a different and much more trustworthy kind of number — but deciding *which section a
block of text belongs to* is still a labeling judgment, made in
[05_song_structure.md](05_song_structure.md), not here.

This module also does not replace `cue_derivation`'s `vocal_band_energy`/`vocal_mask` — that
signal is about *presence* of vocal energy in a frequency band, computed for every track
regardless of language or lyrical content, and nothing about it changes.

---

## 2. Stage placement

Analysis stage, per design-v3 **D6**: expensive (a model forward pass over the full track),
cached, run once per track. Sits alongside `ingestion/feature_extractor` as a new
sibling module — proposed path `src/ingestion/transcription/`. It does **not** depend on
`feature_extractor`'s output and could in principle run in parallel with it, though sharing
the same decoded PCM (rather than re-decoding) is worth deciding at spec time (see Open
Questions).

---

## 3. Proposed design

### 3.1 Cache key

Mirrors `feature_extractor`'s existing pattern exactly, as a new, independent axis:

```
cache key = (content_hash, transcription_version)
```

`transcription_version` is a hand-maintained constant, bumped manually whenever the model,
its config, or its decoding logic changes — the same reasoning `feature_extractor_version`
already exists for: swapping the ASR model must invalidate stale transcripts automatically,
never silently mix cached output from two different model versions.

### 3.2 Model choice

**Local, self-hosted Whisper-family model** (e.g. `faster-whisper`/`whisper.cpp`,
exact variant to be decided at spec time — note that `faster-whisper` has no Metal backend
and is CPU-only on Apple Silicon, so `mlx-whisper` is the likelier runtime here; the exact
model and runtime are the subject of
[`experiments/whisper_bakeoff`](../experiments/whisper_bakeoff/spec.md)). Two reasons this is the right family, both
grounded in this project's own history rather than a generic preference:

- **Self-hosted avoids the rate-limit/auth failure this project has already hit once.**
  `common/llm_service`'s default model (OpenCode Zen's free tier) rejected calls from
  outside the OpenCode app itself (`403 FreeTierError`), forcing a pivot to Gemini's free
  tier. A transcription step that runs once per track, potentially over a large library, is
  exactly the kind of workload that would re-hit a hosted free-tier limit hardest. A local
  model has no such ceiling.
- **Multilingual/code-switched support is a hard requirement, not a nice-to-have** — this
  library is Bollywood material, frequently Hindi/Urdu with English code-switching within a
  single song. Whichever specific model is chosen at spec time must be evaluated against
  that reality before being trusted, not assumed to work because it works on English lyrics.

### 3.3 Output schema (draft)

```
TranscriptionResult:
  content_hash          : str            # matches RawFeatures.content_hash
  transcription_version : str            # cache key partner
  language               : str | None     # detected/declared language, nullable
  segments                 : list[LyricSegment]

LyricSegment:
  start        : float     # seconds, matches design-v3 D20 (float64 seconds everywhere in metadata)
  end            : float
  text             : str
  confidence         : float | None   # nullable soft score, never a hard gate (D10's spirit
                                        # extended to this new signal — see Open Questions)
```

Deliberately **not** included: any "is this a repeated line" or "is this the chorus"
field. Keeping this module's output raw (just what was said, and when) keeps the
repetition/labeling judgment entirely inside
[05_song_structure.md](05_song_structure.md)'s labeling step, so this module stays a pure,
dumb data source — exactly the same relationship `feature_extractor` has to
`cue_derivation`.

### 3.4 Consumers

Only [05_song_structure.md](05_song_structure.md)'s labeling module reads
`TranscriptionResult`, and only as one optional input among several (per-segment summary
stats from `feature_extractor`/`cue_derivation` plus, when available, transcription).
Nothing in Planning or Render ever touches it — same "no model in the planner" boundary
(**D14**) discussed in [02_planning_stage.md](02_planning_stage.md).

---

## 4. Open questions

- **Q1 — Instrumental sections.** Long instrumental stretches (common in film-idiom
  material, per `structure_template == "film"`) will produce empty or garbage ASR output.
  Should this module skip transcription over segments `feature_extractor`'s
  `vocal_band_energy` already marks as low-vocal, both to save compute and to avoid
  hallucinated text on silence? Whisper-family models are known to hallucinate plausible-
  sounding text during non-speech audio.
- **Q2 — Shared decode.** Should this module decode its own PCM independently, or should
  `feature_extractor`'s canonical-format decode (`load_canonical`, 48kHz float32 stereo,
  D25) be reused/shared to avoid two independent "decode this file" implementations
  drifting apart? (`playlist_renderer`'s own spec has an open, structurally identical
  question about `load_audio` — worth resolving both the same way.)
- **Q3 — Segment granularity.** Line-level segments (as drafted above) are what
  repeated-lyric detection needs; word-level timestamps would be more precise but add
  volume and complexity with no identified consumer yet. Line-level is the proposed
  default until a consumer needs finer.
- **Q4 — ASR quality on Hindi/Urdu/code-switched Bollywood lyrics.** Entirely unvalidated.
  This is the single biggest risk to this module's value proposition — if transcription
  quality is poor on this specific repertoire, the repeated-line signal it's meant to
  provide won't be reliable either, and this needs to be measured before real spec work
  proceeds, not assumed. **Being measured by
  [`experiments/whisper_bakeoff`](../experiments/whisper_bakeoff/spec.md)** (draft spec):
  `large-v3` vs `turbo`, raw mix vs separated vocals, auto vs forced language, scored on
  hand-labeled chorus windows. Its verdict also answers Q1 (hallucination on instrumental
  sections) and Q2 (shared canonical decode), and settles the model in §3.2.
  **Alternative under test:**
  [`experiments/lyrics_sourcing`](../experiments/lyrics_sourcing/spec.md) (draft spec)
  is a single-track pipeline that fetches human-written synced lyrics (YouTube Music,
  LRCLIB) first, uses a local Whisper transcript only to validate/correct their timing, and
  falls back to the transcript when nothing usable is fetched. A later multi-track run of
  the same pipeline (its §9 Q6) is what would justify amending this proposal to
  fetch-first, with Whisper as validator and fallback.
- **Q5 — Cache size at scale.** `feature_extractor`'s own spec has an open, unresolved
  question about JSON cache file size at scale for its own per-bar chroma data; full-track
  line-level transcripts add another data volume to the same concern.

---

## 5. Path to a real spec

Once Q1–Q5 have at least provisional answers (particularly Q4 — the
[`whisper_bakeoff`](../experiments/whisper_bakeoff/spec.md) experiment is that spot-check,
and its go/no-go verdict gates this whole promotion),
this file's content promotes into `resources/documentation/ingestion/transcription/spec.md`
via the `write-spec` skill, following this repo's normal naming/storage/amendment
conventions (`resources/documentation/README.md`). At that point this file shrinks to a
short summary-and-link, matching how [01](01_analysis_stage.md) treats every already-built
module.
