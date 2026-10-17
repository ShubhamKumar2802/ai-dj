# Experiments Sandbox

Part of [resources/documentation/pipeline/](00_pipeline_map.md). Documents
`src/experiments/llm_camelot_sequencer/` as it stands today.

---

## 0. What this is, and why it has no module spec

This is a **deliberately standalone** experiment — not wired into the main pipeline, not
covered by `resources/documentation/README.md`'s module-spec convention, and not part of
the automated test suite (it hits a real LLM API and real audio). Its own code states this
explicitly rather than leaving it implicit. It exists to test two hypotheses the
production design defers or rejects, by actually building the rejected/deferred version
and running it against real tracks, rather than reasoning about the outcome in the
abstract. Results from it are **informative, not authoritative** — they inform whether a
real spec is worth writing, they don't substitute for one.

No spec is planned for this experiment as it stands. If a piece of it graduates into a
real design (as [05_song_structure.md](05_song_structure.md)'s labeling module partly
does, informed by this experiment's `structure_llm.py`), that piece gets its own real spec
at that point — the experiment itself stays a sandbox.

---

## 1. `structure_llm.py` — LLM structure detection without chroma

Calls an LLM (via `common/llm_service`) once per track with per-bar telemetry — `rms`,
`spectral_flux`, `low_band_energy`, `vocal_band_energy` — asking it to locate exactly four
timestamps: `intro_end`, `chorus1_start`, `chorus1_end`, `outro_start`. Deliberately
**excludes** `chroma_vector`/`spectral_centroid`/`high_band_energy` from the prompt, on
the stated reasoning that they're mostly harmonic signal, least relevant to structural
segmentation.

Its output is heavily validated after the fact, not trusted raw: every value clamped to
`[0, track.duration]`, `intro_end` falls back to `cue_derivation`'s own
`free_intro_end` if the LLM omits it, `intro_end <= chorus1_start < chorus1_end` is
enforced strictly, a minimum chorus span and minimum playable-length rule are both
checked, and a nonsensical `outro_start` is silently dropped rather than failing the whole
track. This is the concrete evidence cited throughout this pipeline folder for "LLMs are
unreliable at inventing precise numeric boundaries" — even at just four numbers, this much
defensive validation was needed.

**Tension worth resolving before building on this further:** this module's stated reason
for excluding chroma ("least relevant to structural segmentation") is in direct tension
with `overview.md`'s **T8**, which identifies chroma-based self-similarity as *the* real
fix for exactly this problem (a chorus repeats melodically/harmonically — chroma
similarity is precisely a repetition signal). [05_song_structure.md](05_song_structure.md)'s
proposal sides with T8, not with this experiment's exclusion choice.

---

## 2. `camelot_order.py` — Camelot-as-hard-gate sequencer

Deliberately does the opposite of `processing/edge_builder/camelot.py`'s soft
`key_distance` cost: builds a Camelot-adjacency graph and finds an ordering via
backtracking DFS where **every** consecutive pair must be a legal Camelot move (same key,
±1 same letter, or same number with flipped letter) — no exceptions, no relax-to-nearest
fallback. Tracks with an unparseable or missing key are dropped from the candidate pool
entirely, not treated as isolated nodes. If no full ordering exists, it falls back to the
longest partial chain found across every attempted start — a shorter result, not a crash,
but still no relaxation of the hard-gate rule itself.

Its own code states directly that this exists "to test the consequence [of a hard gate]
directly rather than around it" — i.e., to generate real evidence for or against **D10**
("penalties, not filters"), rather than leaving that argument purely theoretical. See
[02_planning_stage.md](02_planning_stage.md) §7 for how this pipeline's design concluded
that question (D10 stands, unchanged).

---

## 3. `mix_builder.py` — bypasses `edge_builder`/`path_search`

Does not use the normal Planning stage at all. For a given Camelot-ordered track sequence,
it calls `edge_builder`'s internal junction-construction helper directly, hard-coding
`strategy_tier = 3` (the only implemented render strategy) and using the LLM's
`chorus1_end` label (§1) as the cue-out point and the next track's `grid_start` as the
cue-in point — i.e., every junction here is a single, externally-decided choice, not a
multi-candidate cost search. It does reuse two small `path_search` utility functions
(feasibility checking, the closer's relaxed fade-out) rather than reimplementing them.

This is a genuinely different pipeline shape from production — no argmin over cue
candidates, no beam search over subset+order — built specifically to isolate and test §1
and §2's two hypotheses against real rendered audio, without the rest of the normal
pipeline's cost machinery in the way.

---

## 4. Results so far, and what they inform

The experiment's own code frames a syntactically-legal-but-musically-nonsensical Camelot
chain as an *expected* possible outcome, not a bug — consistent with this repo's
independent finding that Camelot key estimates on this repertoire can be "confident but
meaningless." No quantitative results from a real run are recorded in this pipeline
folder as of this writing; if/when a run is evaluated, that evidence belongs in
`overview.md`'s open-threads table (or a dedicated amendment to this file), not
duplicated here.

---

## 5. Relationship to production decisions

| This experiment | Production decision it tests | Where the production side lives |
|---|---|---|
| `camelot_order.py`'s hard gate | **D10** — penalties, not filters | [02_planning_stage.md](02_planning_stage.md) §2, §7; `edge_builder` spec |
| `structure_llm.py`'s chroma-free LLM boundaries | **D14** — no model in the planner (this experiment's model call stays correctly in Analysis); T8's chroma-based fix hypothesis | [05_song_structure.md](05_song_structure.md) §1, §2 |
| `mix_builder.py`'s single-choice junctions | **D4** — edge cost embeds the junction search (argmin over candidates, not one externally-decided choice) | [02_planning_stage.md](02_planning_stage.md) §3; `edge_builder` spec |

---

## 6. Sibling experiment: `whisper_bakeoff`

A second sandbox experiment, unlike the one above, **does** have a spec, because its
result gates a production spec rather than testing a design argument:
[`experiments/whisper_bakeoff`](../experiments/whisper_bakeoff/spec.md) (draft) compares
Whisper `large-v3` vs `turbo`, raw mix vs separated vocals, and auto vs forced language on
hand-labeled Bollywood chorus windows. Its go/no-go verdict decides whether
[04_transcription.md](04_transcription.md) is promoted to a real spec. Same sandbox
rules apply: nothing in production imports it, and its results are informative, not
authoritative.

A third, [`experiments/lyrics_sourcing`](../experiments/lyrics_sourcing/spec.md) (draft),
is a single-track, end-to-end pipeline with swappable steps: fetch time-synced lyrics
(Whisper validates their timing, and is the source of truth only when no usable lyrics are
found), pull all built-module metadata, flatten it into a per-second TOON timeline, and ask a
local Ollama LLM to label song structure. Same sandbox rules.

---

## 7. Disposition

Stays sandboxed. No production code path calls into
`src/experiments/llm_camelot_sequencer/`, and none should — its value is as a controlled
test of alternatives this pipeline's design has otherwise only argued for on paper.
