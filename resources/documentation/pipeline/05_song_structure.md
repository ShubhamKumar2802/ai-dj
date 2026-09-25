# Song Structure — Pre-Spec Design Proposal

Part of [resources/documentation/pipeline/](00_pipeline_map.md). **Status: not built.**
This file is a pre-spec design proposal — detailed enough to promote into two real specs
(a `cue_derivation` v2 amendment and a new `resources/documentation/ingestion/
structure_labeler/spec.md`) via the `write-spec` skill, but not yet approved/implemented
as either. Until that promotion happens, this file is the authoritative detail on the
proposal; afterward, it shrinks to a summary-and-link like [01_analysis_stage.md](01_analysis_stage.md).

---

## 0. Why this module

This closes `overview.md`'s open thread **T8**: today's `hook_in`/`hook_exit` is an
energy+vocal-density *proxy* for "the chorus" — real repetition-based structure detection
has been listed as out-of-scope "v2" work in `cue_derivation`'s own spec since it was
first written, and never built. Everything the real fix needs — `chroma_vector`, a 12-dim
per-bar feature — is already computed and cached by `feature_extractor` today; no new
audio-touching analysis is required for the segmentation half of this proposal.

The target output, formalizing the shape sketched during this pipeline's design
discussion:

```
sections:
  - type: intro
    start: 0.0
    end: 17.16
  - type: chorus_or_hook
    start: 58.80
    end: 78.39
  ...

transition_points:
  - time: 58.80
    type: drop
    confidence: high
  ...
```

---

## 1. Division of labor (confirmed split)

Two clearly separated pieces, deliberately in two different modules:

| | Segmentation | Labeling |
|---|---|---|
| **Question answered** | Where are the boundaries, and which segments repeat? | What *is* each segment — intro, chorus, breakdown, drop...? |
| **Method** | Deterministic signal processing (self-similarity over `chroma_vector`) | Model-based judgment (LLM or a typed-decision classifier) |
| **Lives in** | `cue_derivation` v2 (extends the existing module) | A new sibling module, `ingestion/structure_labeler` (proposed name) |
| **Touches a model?** | No | Yes — the only place in this whole proposal a model call happens |
| **Why here** | Consistent with `cue_derivation`'s existing "never touches audio, never touches a model" invariant — this is pure signal processing over metadata already in `RawFeatures` | Mirrors how `familiarity_scorer` is a separate `llm_service` consumer rather than living inside `path_search` — keeps every model call isolated to its own clearly-bounded module, never buried inside a module whose invariant promises otherwise |

The reason this split matters, not just a style preference: **inventing precise
boundary timestamps is exactly the failure mode a model is bad at** (see
[04_transcription.md](04_transcription.md) §1's non-goals, and
[06_experiments_sandbox.md](06_experiments_sandbox.md)'s `structure_llm.py`, which needs
heavy clamping/validation for just four numbers). Keeping boundary-finding entirely
deterministic and giving a model only the *already-detected* segments to label removes
that failure mode from the part of the system most exposed to it.

Both halves stay strictly inside the Analysis stage — this split does not change where
model calls are allowed to happen (**D14**, "no model in the planner"): only the specific
module that's allowed to touch one changes.

---

## 2. Segmentation — `cue_derivation` v2

**Input:** `RawFeatures.per_bar_features[].chroma_vector` — already computed by
`feature_extractor` (Essentia `NNLSChroma`, 12-dim per bar) and already read by
`cue_derivation`'s existing phrase-boundary detector. No new upstream extraction work.

**Technique:** a full pairwise self-similarity matrix (SSM) over per-bar chroma across the
whole track — distinct from the *local* Foote-checkerboard novelty curve `phrase_grid`
already computes (which finds "this point differs from its immediate neighbors," i.e.
boundary locations only). The SSM finds the complementary signal: off-diagonal stripes
reveal which non-adjacent bars/segments share harmonic content — i.e., which sections
*repeat*. This is squarely a v2 idea design-v3 already names (§6.3, "Step 3 — SSM for
repetition") but never implements.

**Output — extends `CueDerivationResult`:**

```
SegmentationResult:                     # new fields on CueDerivationResult, v2
  transition_points : list[RawTransitionPoint]

RawTransitionPoint:
  time                : float
  novelty_strength      : float           # existing phrase_grid signal, carried through
  repetition_cluster       : int | None      # which recurring-content group this segment
                                              # belongs to; None if it doesn't repeat
                                              # anywhere else in the track
```

This is deliberately **unlabeled** — `RawTransitionPoint` says "a boundary is here, and
here's what else in the track sounds like it," never "this is a chorus." That judgment is
[§3](#3-labeling--new-module-ingestionstructure_labeler-proposed-name) below.

**Why this is a version bump, not an amendment**, per `resources/documentation/README.md`'s
rule: it changes `CueDerivationResult`'s public contract (a new field), so code already
built against v1 of the spec would need to change to consume it — the exact test the
README uses to distinguish a version bump from an amendment.

---

## 3. Labeling — new module (`ingestion/structure_labeler`, proposed name)

**Inputs:**
- `RawTransitionPoint[]` from §2 (where the boundaries are, and which repeat)
- Per-segment summary stats already available on `Track`/`RawFeatures` — energy level,
  vocal density, spectral characteristics, for the bars inside each segment
- Optionally, `TranscriptionResult` from [04_transcription.md](04_transcription.md) —
  repeated lyric lines are an independent, strong vote for "this is the chorus," on top of
  the repetition-cluster signal from segmentation

**Candidate approaches, and what's recommended:**

1. **An LLM call via the existing `common/llm_service`** — the same infrastructure
   `structure_llm.py` (see [06](06_experiments_sandbox.md)) and the not-yet-built
   `familiarity_scorer` already use: `generate(request, output_schema)` with a
   `pydantic.BaseModel` output schema, one call per track, cached the same way
   `familiarity_scorer` calls would be. This is the lower-effort option — it reuses
   infrastructure that already exists, already handles retries/caching/logging, and
   already enforces structured output.

2. **A non-autoregressive typed-decision classifier** (the "Jev/Laya" class of model
   discussed during this pipeline's design) — instead of free-text generation, a single
   forward-pass classifier answers a fixed set of typed questions per segment (a `choice`
   among section types, a `score`/`noul` for things like "is this a drop"), returning a
   calibrated confidence with each answer. Two real advantages over option 1: much lower
   per-call latency (~33ms vs. a full LLM round-trip) and no free-text generation to
   hallucinate from. Two real costs: it doesn't fit `llm_service`'s existing
   `generate(request, output_schema)` Protocol at all (its actual interface is
   `Router.predict(state, questions)`), so it would need its own small module rather than
   slotting into existing infrastructure; and as of this writing this class of model is
   about a week old with no track record, and its own publisher's benchmark shows a large
   zero-shot-vs-fine-tuned accuracy gap (0.362 → 0.766) — meaning it would very likely need
   a hand-labeled fine-tuning set from this project's own material before being trustworthy,
   the same cold-start problem either approach eventually faces for a domain this
   specific (Bollywood song structure).

**Recommendation:** start with option 1 (reuses proven infrastructure, no cold-start data
problem), and treat option 2 as a possible later swap — the interface between
`structure_labeler` and its caller (`Track` gains `sections[]`) doesn't change either way,
only what's inside the module does.

**Output:**

```
StructureLabels:
  sections           : list[Section]

Section:
  type       : str          # "intro" | "build" | "high_energy" | "breakdown" |
                             #  "lower_energy" | "chorus_or_hook" | ... (open — see Q2)
  start        : float
  end            : float
  confidence       : float | None    # nullable soft score (D10's spirit, extended)
```

`transition_points[]` in the final output (matching the sketch in §0) is derived by
this module too — it enriches each `RawTransitionPoint` from segmentation with a
semantic `type` (`"energy_up"`, `"breakdown"`, `"drop"`, `"energy_peak"`, `"outro"`, ...)
and, where warranted, a qualitative `confidence` tag, the same way it types `sections[]`.

---

## 4. Proposed schema

Putting §2 and §3 together, `Track` gains:

```
Track.sections           : list[Section]            # from structure_labeler
Track.transition_points   : list[TransitionPoint]      # from structure_labeler,
                                                          # built on segmentation's raw points

TransitionPoint:
  time         : float
  type           : str            # "energy_up" | "breakdown" | "drop" | "energy_peak" |
                                    # "outro" | ...
  confidence       : str | float | None   # qualitative ("high") or numeric — pick one at
                                            # spec time (see Q3)
```

---

## 5. Consumers

Not redesigned here — future work. Once real, `edge_builder`/`path_search` could
eventually score a junction against an actual `chorus_or_hook` section instead of the
`hook_exit` proxy, or use `transition_points` typed `"drop"`/`"breakdown"` as stronger
cue-kind candidates. Any such change is a Planning-stage spec change in its own right,
made after this data exists and can be evaluated against real tracks — not assumed here.

---

## 6. Open questions

- **Q1 — Cluster count / threshold.** Self-similarity clustering is unsupervised; how many
  repetition clusters a track "should" have, and what similarity threshold counts as "the
  same section," has no ground truth yet in this codebase (mirrors `edge_builder`'s own
  open question about `phrase_grid`'s novelty strength saturating on real data — expect a
  similar hand-tuning-against-real-tracks phase).
- **Q2 — Section type vocabulary.** The exact set of `Section.type` values (the sketch
  above uses `intro`/`build`/`high_energy`/`breakdown`/`lower_energy`/`chorus_or_hook`) is
  provisional — needs reconciling against `cue_derivation`'s existing `CueKind` enum
  (which already has unused `chorus_start`/`chorus_end` values, seemingly reserved for
  exactly this) before a real spec is written, so the two vocabularies don't drift apart.
- **Q3 — Confidence representation.** Numeric `[0,1]` (consistent with **D26** and every
  other confidence in this codebase) vs. the qualitative `"high"` shown in the original
  sketch — should be numeric for consistency, with a qualitative label as a display-only
  derived value if one is wanted at all.
- **Q4 — Compute cost.** A full O(n²) self-similarity matrix over per-bar chroma is cheap
  at typical track lengths (hundreds of bars, not thousands) but unverified at scale
  across a large library — worth a quick measurement before committing to the approach in
  a real spec.
- **Q5 — Should this be evaluated experimentally first?** Given
  [06_experiments_sandbox.md](06_experiments_sandbox.md)'s precedent (this repo tests
  hypotheses in a sandboxed experiment before writing a real spec when the answer is
  genuinely unknown), a similar throwaway experiment comparing option 1 vs. option 2 from
  §3 on a handful of real tracks may be worth doing before committing to a real spec here.

---

## 7. Path to a real spec

Segmentation (§2) promotes into a `cue_derivation` **v2** — following
`resources/documentation/README.md`'s version-bump convention (`archive/spec-v1.md`, new
`spec.md` content, a `**v2** — supersedes v1` header). Labeling (§3) promotes into a new
`resources/documentation/ingestion/structure_labeler/spec.md`, following the same
naming/storage convention as every other module. Both promotions go through the
`write-spec` skill once Q1–Q5 above have at least provisional answers.
