# Cue Derivation — Spec

**Layer:** `ingestion/` — second module in this layer, downstream of `feature_extractor`.
**Depends on:** `resources/documentation/ingestion/feature_extractor/spec.md`'s
`RawFeatures` contract.

---

## 0. Invariant

> **This module never touches audio.** It is a pure function of `RawFeatures` —
> `derive_cues(raw: RawFeatures) -> CueDerivationResult` — cheap, milliseconds, safe
> to rerun on every tuning change. If any code path here needs a waveform, the design
> has broken (design-v3 D2's metadata-only invariant, one layer earlier than planning).

This is the cheap, volatile half of design-v3 D6's cache boundary: boundary
detection, phrase grid, `hook_exit`/`hook_in`, cue emission, and quarantine all
belong here specifically *because* they're expected to be re-tuned constantly without
re-paying `feature_extractor`'s decode + DSP cost.

---

## 1. Scope & consumers

Produces the remainder of `Track` (design-v3 §5.1) that `feature_extractor`'s spec
table didn't already assign:

| `Track` field | Owned here |
|---|---|
| `grid_start`, `grid_confidence`, `free_intro_end` | §3 |
| `phrase_length_bars`, `phrase_grid[]` | §4 |
| `structure_template` | §5 |
| `cue_ins[]`, `cue_outs[]` | §6, using `hook_exit`/`hook_in` from §7 |
| `status` | §8 |

**Explicitly out of scope — a boundary worth stating precisely:**

- **D24's first/last-track relaxation (free cue-in on track 0, free cue-out on
  track N−1) is *not* implemented here.** This module processes one track at a time
  with no notion of mix position — it cannot know whether a given track will end up
  first, last, or in the middle of a `MixPlan`. D24 is applied by whatever assembles
  the mix (edge builder / path search, not yet specced), which relaxes the
  constraint for whichever tracks it happens to place at the ends. This module always
  emits cue candidates as if the track could appear mid-set; **D9/D10's hard
  constraint ("no cue before `grid_start`") applies unconditionally to every cue this
  module emits**, without exception.
- SSM repetition analysis and full section labelling (both v2, §6.3 Steps 2–3) —
  `hook_exit`/`hook_in` (§7) need boundaries and energy/vocal thresholds only, not a
  self-similarity matrix or a trained/decoded label sequence.
- Vocal-mask *computation* — `RawFeatures.vocal_band_energy[]` becomes
  `Track.vocal_mask[]` unchanged (feature_extractor spec §9); this module only reads
  it to place cues (§7), never recomputes it.
- Assembling the final `Track` object (merging this module's output with
  `RawFeatures`, `id`, `path`, and `common/llm_service`'s familiarity fields) — that's
  an ingestion orchestrator's job, not yet specced.

---

## 2. Data contract — `CueDerivationResult` (`schema.py`)

```
CueDerivationResult:
  grid_start          : float
  grid_confidence       : float
  free_intro_end          : float

  phrase_length_bars        : float | None   # advisory only (D8) — never projected
  phrase_grid                 : list[PhraseBoundary]

  structure_template             : "edm" | "film" | "unknown"

  cue_ins                          : list[Cue]
  cue_outs                          : list[Cue]

  status                              : "ok" | "cut_only" | "excluded"
  cue_derivation_version                : str   # hand-maintained, mirrors
                                                  # feature_extractor_version (§9)

PhraseBoundary:
  position            : float
  strength              : float
  bars_since_previous     : float | None   # None for the first detected boundary

Cue:
  position     : float
  kind          : CueKind
  confidence      : float

CueKind = (
  "first_downbeat" | "intro_end" | "chorus_start" | "chorus_end" | "interlude_start" |
  "outro_start" |
  "riser_start" | "hook_in" |                    # cue-in only
  "hook_exit" | "time_boxed"                     # cue-out only
)
```

`CueKind` uses design-v3's amended vocabulary (`## 14. Amendments`,
2026-08-16): `chorus_start`/`chorus_end` (was `mukhda_start`/`mukhda_end`).
`interlude_start`, `first_downbeat`, `intro_end`, `outro_start` are unchanged from
§1.5 — no Western-pop equivalent needed for interlude, and the others were never
mukhda/antara-specific.

---

## 3. Grid origin (`grid_origin.py`)

Per D9: `grid_start = raw.downbeat_times[0]` — the first *detected* downbeat, not
file start (F3: unpulsed intros give onset detection nothing to fire on; a grid
anchored at 0:00 is meaningless as a cue candidate). `grid_confidence =
raw.downbeat_confidence`, passed straight through — this module has no independent
signal to improve on `feature_extractor`'s own honesty about downbeat-phase
uncertainty (feature_extractor spec §6).

**`free_intro_end` — a simplifying v1 decision, stated explicitly rather than left
implicit:** set equal to `grid_start` unless `raw.riser_candidates` contains a
candidate starting before `grid_start`, in which case `free_intro_end =
riser_candidates[0].start_time` — marking where the free-time region's usable
transition material (the riser, F4) begins, rather than where the beat grid becomes
trustworthy. Design-v3 doesn't give a formula distinguishing these two fields beyond
naming them separately in §5.1; this is the most defensible reading and is flagged in
§10 as an open question, not a settled interpretation.

---

## 4. Phrase boundary detection (`phrase_grid.py`)

D8's rule: **detect boundaries locally; never project a grid.** `phrase_length_bars`
is advisory only (a summary statistic over detected gaps, e.g. median
`bars_since_previous`) — nothing downstream may use it to *predict* where the next
boundary is (F2: section lengths follow lyrics/production, not a periodicity prior;
a projected grid silently desyncs after any metric irregularity).

**Technique: a novelty curve via Foote's checkerboard kernel** (§6 ML-strategy
table: "Foote checkerboard on per-bar features... No" — no training required),
convolved along the diagonal of a local self-similarity window built from
`raw.per_bar_features`' six fields (`rms`, `spectral_centroid`, `spectral_flux`,
`low_band_energy`, `high_band_energy`, `chroma_vector`) at each bar position. Peaks
above a threshold become `PhraseBoundary` entries; peak height is `strength`.

**Distinct from v2's SSM repetition analysis (§6.3 Step 3).** That technique builds
a *full* pairwise self-similarity matrix to find distant, non-adjacent repeated
sections ("bars 33–48 are the same material as 97–112") — a different question
("which sections repeat") from this module's ("where does a section end"). This
module only ever looks at a local window around each candidate boundary; it never
computes the full N×N matrix.

---

## 5. `structure_template` classification (`structure_template.py`)

**A coarse v1 heuristic, explicitly not §6.3 Step 2's template-constrained
decoding** (that's v2 — Viterbi over a label grammar with hand-set duration priors;
this module does neither of those things). v1 signal, from data already in
`RawFeatures`/§4's output only:

- `free_intro_end` relative to track duration (a long beatless intro/outro is house's
  DJ-padding convention, §1.4) — a track with `free_intro_end` past some threshold
  (default 8 bars-worth of seconds at the track's own `bpm`) reads as `edm`-leaning.
- Regularity of `phrase_grid[]` spacing — consistent 8- or 16-bar
  `bars_since_previous` reads `edm`; irregular or long (~12-bar, F8) spacing reads
  `film`.
- Neither signal clears its threshold confidently → `unknown`.

This directly gates D5's tier-penalty conditioning and D27's cue-kind preference
order downstream (in the edge builder, out of scope here) — so it's load-bearing
despite being a heuristic. Flagged in §10 as needing real tuning against
design-v3's own club-edit vs. film-master test set (D11).

---

## 6. `hook_exit` / `hook_in` (`hook.py`)

D27, verbatim formula, computed from `raw.energy_curve[]` and
`raw.vocal_band_energy[]` (→ `Track.vocal_mask[]`, unchanged from feature_extractor)
against `phrase_grid[]` boundaries from §4:

```
hook_exit = first phrase boundary where
              energy_curve[] drops significantly
              AND vocal_band_energy[] drops
            occurring after a sustained high-energy vocal region
            of at least ~8 bars

hook_in   = onset of that same first sustained high-energy, high-vocal plateau
            (the symmetric entry-side detector)
```

"Significantly" / "sustained" / "high-energy" are threshold constants on
`CueDerivationConfig` (§9) — hand-tuned defaults, not derived. No SSM, no
segmentation model (§6.3: "roughly a day's work" is the doc's own estimate for this
detector's actual complexity) — pure thresholding over two arrays already computed
by `feature_extractor`.

---

## 7. Cue emission (`cues.py`)

Preference orders, from D27/§7.1, cue-kind names per the amended vocabulary (§2):

```
cue_in:   intro / riser_start    — when free_intro_end indicates real DJ padding
                                    (structure_template == "edm")
          hook_in                — when it doesn't (film, genre switch, unknown)
          grid_start              — guaranteed fallback

cue_out:  hook_exit               — preferred, musical (§6)
          outro_start               — when a real outro is detected and the time
                                        budget allows
          time_boxed                 — guaranteed fallback: first phrase boundary
                                        after `config.time_box_bars` bars from
                                        cue-in, minimizing vocal presence (D22) —
                                        needs only phrase_grid[], which this module
                                        already computes
```

**Hard constraint, unconditional** (§1, D9/D10): no cue in `cue_ins[]`/`cue_outs[]`
ever has `position < grid_start`. `riser_start`, when present, is the sole cue kind
allowed to originate before `grid_start` as a *candidate* — but note `grid_start`
itself is defined as the first downbeat, so a `riser_start` cue naturally precedes it
by construction; this is the D9-documented exception, not a violation.

`time_box_bars` default: `32` (D27's own arithmetic — intro 8 + buildup 8 + hook 16
≈ 32 bars ≈ 58s at 132 BPM, close to the ~67s/track reference). A `CueDerivationConfig`
field, not a hardcoded literal — see §9.

---

## 8. `status` quarantine (`status.py`)

D7: "a wrong beat grid poisons every edge it touches." v1 thresholds, all on
`CueDerivationConfig` (§9), applied to `grid_confidence` (§3) primarily —
`key_confidence` is explicitly excluded from this decision (D10: key is a soft score,
never a gate, even a demoting one):

```
status = "excluded"  if grid_confidence < config.exclude_threshold
                        # beat grid unusable — nothing built on it can be trusted
       = "cut_only"   elif grid_confidence < config.cut_only_threshold
                        # usable for tier-3 cut-on-the-1; not confident enough for
                        # a bass-swap anchor
       = "ok"         otherwise
```

`cut_only` is a signal consumed by the (out-of-scope) edge builder to restrict which
strategy tiers are eligible for this track's junctions — this module only assigns
the label, it doesn't enforce the tier restriction itself.

---

## 9. Orchestration & config (`derive.py`, `config.py`)

```
CueDerivationConfig:
  cue_derivation_version : str    # hand-maintained (mirrors feature_extractor's
                                   # version pattern — no auto-derivation)
  time_box_bars           : int    # default 32 (§7)
  hook_min_bars             : int   # default 8 (§6)
  exclude_threshold           : float  # default TBD — see §10
  cut_only_threshold             : float  # default TBD — see §10
  edm_intro_bars_threshold          : int  # default 8 (§5)

derive_cues(raw: RawFeatures, config: CueDerivationConfig) -> CueDerivationResult
  1. grid_start, grid_confidence, free_intro_end = derive_grid_origin(raw)   # §3
  2. phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw)          # §4
  3. structure_template = classify_structure_template(raw, free_intro_end,
                                                        phrase_grid, config)    # §5
  4. hook_in, hook_exit = detect_hook(raw, phrase_grid, config)                 # §6
  5. cue_ins, cue_outs = emit_cues(raw, grid_start, free_intro_end,
                                    structure_template, hook_in, hook_exit,
                                    phrase_grid, config)                          # §7
  6. status = quarantine(grid_confidence, config)                                 # §8
  7. assemble CueDerivationResult
```

No caching layer — this module is the cheap, volatile half of D6's split precisely so
it *doesn't* need one; rerun on every config/threshold change.

---

## 10. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | `free_intro_end`'s formula (§3) is a v1 simplifying decision (equals `grid_start` unless a riser precedes it) — is this actually what design-v3's separate naming of the two fields intended? | Correctness of §3, low blast radius (one field) |
| Q2 | `exclude_threshold`/`cut_only_threshold` (§8, §9) have no principled default yet — design-v3 §6.5 itself calls the equivalent judgment "currently a hand-tuned heuristic threshold" pending the (v2) grid-confidence model | Needs real tracks run through `feature_extractor` to set sane defaults empirically |
| Q3 | `structure_template`'s two-signal heuristic (§5) hasn't been validated against design-v3's own club-edit vs. film-master test set (D11) | Whether D5's tier-penalty conditioning and D27's cue-kind preference order get the right signal in practice |
| Q4 | Should `hook_exit`/`hook_in` thresholds (§6) vary by `structure_template`, given Bollywood's vocal density is 70-80% (D22) vs. EDM's much lower baseline — does one fixed "significant drop" threshold work for both? | §6's threshold constants — currently assumed template-agnostic |

---

## 11. File layout

```
src/ingestion/cue_derivation/
  __init__.py              # public exports: CueDerivationResult, PhraseBoundary,
                            # Cue, CueKind, CueDerivationConfig, derive_cues
  schema.py                 # CueDerivationResult, PhraseBoundary, Cue, CueKind (§2)
  config.py                  # CueDerivationConfig (§9)
  grid_origin.py               # derive_grid_origin() (§3)
  phrase_grid.py                 # detect_phrase_boundaries() — Foote checkerboard (§4)
  structure_template.py            # classify_structure_template() (§5)
  hook.py                            # detect_hook() — hook_exit/hook_in (§6)
  cues.py                              # emit_cues() (§7)
  status.py                             # quarantine() (§8)
  derive.py                               # derive_cues() orchestrator (§9)

tests/ingestion/cue_derivation/
  conftest.py                 # synthetic RawFeatures fixtures (JSON-constructible —
                               # this module's whole point is testability without
                               # audio, per D2/§0; fixtures are hand-built RawFeatures
                               # instances, never real tracks)
  test_schema.py               # (only if validation logic exists beyond field types)
  test_grid_origin.py            # grid_start/grid_confidence/free_intro_end, incl.
                                  # the riser-precedes-grid_start case (§3)
  test_phrase_grid.py              # novelty-curve boundary detection on synthetic
                                    # per-bar feature sequences with known boundaries
  test_structure_template.py         # edm/film/unknown classification cases (§5)
  test_hook.py                         # hook_exit/hook_in on synthetic energy/vocal
                                        # curves with known plateaus (§6)
  test_cues.py                           # preference-order selection; hard
                                          # constraint (no cue before grid_start) (§7)
  test_status.py                           # threshold boundary cases (§8)
  test_derive.py                             # orchestration, assembled
                                              # CueDerivationResult shape
```

Every test file here is a **millisecond, no-audio, JSON-fixture test** (D2) — this is
the concrete payoff of splitting this module out from `feature_extractor` at all.

---

## 12. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Apply D24's first/last-track cue relaxation here | Emit cues as if the track could be mid-set always; relaxation applied by the (out-of-scope) mix assembler | This module processes one track at a time and has no notion of mix position — it cannot know if a track will land first or last |
| Full SSM pairwise self-similarity matrix for boundary detection | Foote checkerboard novelty curve over a local window (§4) | SSM answers "which distant sections repeat" (v2, §6.3 Step 3); this module only needs "where does a section end," a cheaper, more local question |
| `structure_template` via §6.3 Step 2's template-constrained Viterbi decode | A coarse two-signal heuristic (§5) | That's explicitly v2 scope in design-v3; v1 needs *some* signal to gate D5/D27 now, not the full grammar-based decoder |
| Recompute or reinterpret `vocal_band_energy[]` here | Pass through unchanged as `Track.vocal_mask[]`; only read it to place cues (§1, §6) | Keeps the audio-derived signal's computation in exactly one place (`feature_extractor`), matching this module's own metadata-only invariant (§0) |
