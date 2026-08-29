# Module overview

Two things live here: a **working order** (what to do next, and why that order) and a
**coverage table** (what exists, against `resources/ai-dj-design-v3.md` §4 and §10).

**Neither is auto-generated, so both can drift.** Re-check against the design doc and
the module specs before trusting the status columns. Update this file as each spec or
implementation lands — that is the point of it.

Last checked: 2026-08-24.

---

## Working order

Where things stand: **the analysis layer is built and working, the planning layer is
fully specced with one module unimplemented, and the render layer has no code at all**
(`src/render/` does not exist). So nothing produced so far can be listened to yet.

The critical path to a mix you can actually hear is **W1 → W2 → W3**.

### W1 — Implement `processing/path_search` · build step 5

| | |
|---|---|
| **Blocked by** | nothing — spec approved 2026-08-24 |
| **Unblocks** | real `MixPlan`s instead of hand-typed fixtures; W3 |
| **Done when** | `examples/example_search_path_from_music.py` prints a 15-track ordering with its five objective terms, `tier_histogram` and `estimated_duration_s` |

Completes the planning layer end-to-end (`audio → Track[] → ScoredEdges → MixPlan`).
The spec pins every file, signature and test — `processing/path_search/spec.md` §12–13.
Watch the four items its §12 calls out as silent-failure tests (feasibility, objective
scale, beam length uniformity, `K_eff` clamping); each exists because the bug it
catches would otherwise ship looking like success.

### W2 — Render Milestone A · build step 0, the walking skeleton

| | |
|---|---|
| **Blocked by** | nothing — both render specs are Milestone-A complete |
| **Unblocks** | hearing *anything*; W3 |
| **Done when** | one rendered WAV from a 2-track, 1-junction, tier-3 `MixPlan` |

design-v3 §10 puts this **first**, before any search, precisely so "the renderer works,
so real cue points plug into something already functioning." It was skipped; steps 1–4
were built instead. That is why there is currently a complete planner and no way to
hear its output. Tier 3 only — `length_bars = 0` degenerates to a splice, so this needs
no EQ, no envelopes, no time-stretch.

### W3 — Render Milestone B · multi-junction assembly

| | |
|---|---|
| **Blocked by** | W1 (real plans) + W2; and a design decision — `playlist_renderer` §9 **Q1**: does this module slice each track's body, or does `transition_renderer` grow a "max duration for B" parameter? |
| **Unblocks** | **the first full mix you can hear.** Also `fade_out_bars` (Q3), set-wide LUFS gain, and W6's tuning |
| **Done when** | a 15-track `MixPlan` renders to one continuous WAV |

Q1 was explicitly deferred "until `edge_builder`/`path_search` exist." Both now do, so
it is answerable — resolve it in the spec before writing the loop.

### W4 — Fix `downbeat_confidence` · `feature_extractor` §6

| | |
|---|---|
| **Blocked by** | **a decision, not code** — see Open threads T1 |
| **Unblocks** | tier 2 eligibility, and therefore any blended transition at all |
| **Done when** | quarantine rate is defensible on the 69-track corpus, thresholds recalibrated, `extractor_version` bumped, cache re-extracted |

Independent of W1–W3 and can slot in anywhere once decided. Placed after W3 only
because its *quality* effect is unjudgeable until a mix can be heard — though its
*measurable* effects (quarantine rate, tier-2 eligibility, `% at tier 2`) are visible
without listening.

### W5 — Tier 2/4/5 rendering · `transition_renderer` Milestone B

| | |
|---|---|
| **Blocked by** | W3, and W4 for tier 2 specifically (until quarantine is fixed, tier 2 is never selected) |
| **Unblocks** | actual bass swaps; `% at tier 2` becoming a meaningful health metric (D5) |
| **Done when** | a tier-2 junction renders correctly — 3-band EQ, envelope interpretation, `rate_b` time-stretch |

`Junction.bar_seconds` (`edge_builder` v2) is already in place, so the bars→samples
conversion this needs is solved.

### W6 — Tune weights and tier penalties

| | |
|---|---|
| **Blocked by** | W3 — this is the deferred "decide after hearing a rendered mix" |
| **Unblocks** | D26's blind period, which currently gates output quality across three modules |
| **Done when** | λ/μ/ν/β and the tier-penalty tables have been set against real output rather than guessed |

Covers `path_search` §15 Q5 (λ/μ/ν/β), `edge_builder` §12 Q3 (the seven `w_*`), and the
open question of whether `tier_penalties_film` should prefer blends over cuts (T2).
design-v3 §8 lists untunable weights as a standing project risk; §9 defines the metrics.

### W7 — `ingestion/familiarity_scorer` · build step 8

| | |
|---|---|
| **Blocked by** | nothing technically; `common/llm_service` is built |
| **Unblocks** | `path_search`'s `ν` term, currently inert because every `familiarity_score` is `None` |
| **Done when** | `Track.familiarity_score`/`.era`/`.is_club_edit` are populated and `familiarity_deficit` stops being constant |

Deliberately last in design-v3's own build order. `path_search` §7 is written so this
becomes a **data** change, not a code change.

---

## Build order — design-v3 §10 coverage

`Spec` and `Code` are tracked separately on purpose: several modules are fully specced
with no implementation.

| Step | Module | design-v3 ref | Spec | Code |
|---|---|---|---|---|
| — | `acquisition/youtube_downloader` — new layer upstream of `ingestion/`, not in design-v3's build order; produces the local paths `ingestion/orchestrator` consumes | — | Done | Done |
| 0 | Walking skeleton — exercises Milestone A of #6 + #7 | §10 | Done | **— (W2)** |
| 1 | `ingestion/feature_extractor` — **spec v3**; §6's `downbeat_confidence` is defective, see T1 | D6, D25 | Done | Done |
| 2 | Per-bar feature stack — folded into `feature_extractor` §7, not its own module | §6.3 step 1 | Done (in #1) | Done (in #1) |
| 3 | `ingestion/cue_derivation` | D8/D9/D22/D27 | Done | Done |
| — | `ingestion/orchestrator` — glue for §4's `RawFeatures → Track[]` arrow; no step number, sits between #3 and #4 | §4 | Done | Done |
| 4 | `processing/edge_builder` — **spec v2** (`Junction.bar_seconds`; v1 in `archive/spec-v1.md`) | D4/D5/D19 | Done | Done |
| 5 | `processing/path_search` — owns `MixPlan`/`TrackRef`/`MixPlanConfig` in `common/contracts/` | D3/D21 | Done | **— (W1)** |
| 6 | `render/transition_renderer` — Milestone A **specced**, Milestone B (tiers 2/4/5, LUFS, tempo lock) documented | D17 | Done | **— (W2/W5)** |
| 7 | `render/playlist_renderer` — Milestone A **specced**, Milestone B (multi-junction, MP3, CUE sheet) documented | D17 | Done | **— (W2/W3)** |
| 8 | `ingestion/familiarity_scorer` — calls `llm_service`, writes `Track.familiarity_score`/`.era`/`.is_club_edit` | §6.1 | — | **— (W7)** |

## Infrastructure (`common/`)

Cross-cutting, built ahead of the build order, no step number.

| Module | Spec | Code |
|---|---|---|
| `common/contracts` — `Junction`, `Envelope`, and (per `path_search` §2) `MixPlan`, `TrackRef`, `MixPlanConfig` | Owned by producing modules | Partial — `MixPlan` lands with W1 |
| `common/llm_service` | Done | Done |
| `common/logging` | Done | Done |

---

## Open threads

Cross-cutting findings that are not modules. Each is logged in full in a spec — this
is a pointer list, not a second copy.

| # | Thread | Status | Logged in |
|---|---|---|---|
| T1 | **`downbeat_confidence` is mis-scaled**, quarantining 86% of the corpus and making tier 2 unreachable. Root cause diagnosed; `pair_contrast` replacement validated on 69 tracks (median `0.053` → `0.168`); multi-band and chroma alternatives tested and **failed**. Needs a decision: `pair_contrast` alone, or also add a DBN downbeat tracker | **Decision pending** — blocks W4 | `feature_extractor` §16 Q1 + 2026-08-24 amendment |
| T2 | **Half-bar downbeat ambiguity** — beats 1 and 3 both carry kick, so the chosen phase is near-arbitrary. Was masked by T1's over-quarantining. Matters for tier 2: a swap at "bar 8" lands two beats out on a shifted grid | Open, unmeasured | `feature_extractor` §16 Q5 |
| T3 | **Quarantine thresholds need recalibrating** if T1's metric is replaced — `pair_contrast`'s floor (`0.027`) sits above `exclude_threshold` (`0.01`), which would make `status="excluded"` unreachable | Coupled to T1 | `cue_derivation` §10 Q2 + 2026-08-24 amendment |
| T4 | **Should the tier ladder prefer blends over cuts for film material?** §1.9 says tiers 3–4 are the *correct* idiom for film masters, not a degradation. Deferred until a mix can be A/B'd | Deferred to W6 | `edge_builder` §12 Q10 |
| T5 | **Weights are untunable until an eval harness exists** (D26). Affects `edge_builder`'s seven `w_*`, `path_search`'s λ/μ/ν/β, and both tier-penalty tables | Blocked on W3/W6 | `edge_builder` §12 Q3/Q8, `path_search` §15 Q5 |
| T6 | **`test_concurrent_calls_for_same_key_extract_once` flaked once** under heavy CPU load (68s run vs 25s baseline), passed 3/3 in isolation and twice since. Not a regression — no `feature_extractor` code changed | Watch; revisit if it recurs in CI | not logged in a spec — here only |

## Deliberately not counted as gaps

Real design-v3 concepts, but not v1 modules — don't re-flag these as missing without
re-checking the doc first:

- Grid-confidence calibration model (§6.5) — explicitly v2. **Note:** T1 is *not* this;
  it is a defect in the v1 heuristic, not the absence of the v2 model.
- Template-constrained decoding / SSM repetition / section labelling (§6.3 Steps 2–3) — v2.
- Tempo ramping (D18) — "v1 status: not needed."
- Natural-language mix-config parsing (§6.1) — "interface sugar," deferred.
- Junction-preview / eval harness (§9) — a dev tool that falls out of D17's testability
  property for free, not a pipeline module. **But** T5 means W6 needs some form of it.
