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

**Exception: `raw.downbeat_times` empty** (see `## Amendments`) —
`feature_extractor`'s `_detect_downbeats` returns `([], 0.0)` whenever fewer than
`beats_per_bar * 2` beats are detected, so the naive formula above would raise
`IndexError` on exactly the track this module most needs to quarantine cleanly.
In that case: `grid_start = 0.0`, `grid_confidence = raw.downbeat_confidence`
(already `0.0` by `feature_extractor`'s own contract), `free_intro_end = 0.0` —
this still flows correctly into `status="excluded"` at §8 instead of crashing.

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
at or above `novelty_curve.mean() + config.phrase_boundary_novelty_std_multiplier *
novelty_curve.std()` become `PhraseBoundary` entries (see `## Amendments` — this
config field didn't exist before); peak height is `strength`. `detect_phrase_boundaries`
therefore takes `config` as a parameter (§9's orchestration step 2 is amended to match).

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
  `film`. Formalized as: coefficient of variation (stdev/mean) of
  `bars_since_previous` below `config.phrase_regularity_cv_threshold` reads
  "regular"/`edm`-leaning (see `## Amendments` — this config field didn't exist
  before); this signal abstains (no vote) when fewer than 2 `phrase_grid` gaps
  exist.

**Combination rule** (see `## Amendments` — only the "neither clears" case was
previously stated): the intro-length signal always votes (duration/`free_intro_end`
are always defined, so it never abstains); the regularity signal may abstain per
above.

```
regularity signal abstains             -> use intro-length signal's vote
both signals present and agree         -> that template
both signals present, disagree         -> "unknown"
```

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
hook_exit_candidates = every phrase boundary at or after the end of a
            sustained high-energy vocal region of at least ~8 bars — no
            upper bound on the search, no per-boundary drop check (see
            ## Amendments, 2026-09-17)

hook_in   = onset of that same first sustained high-energy, high-vocal plateau
            (the symmetric entry-side detector)
```

"Significantly" / "sustained" / "high-energy" are threshold constants on
`CueDerivationConfig` (§9) — hand-tuned defaults, not derived. No SSM, no
segmentation model (§6.3: "roughly a day's work" is the doc's own estimate for this
detector's actual complexity) — pure thresholding over two arrays already computed
by `feature_extractor`.

**Formula, spelled out precisely** (see `## Amendments` — these five config fields
and this exact procedure didn't exist before). All thresholds are **per-track-relative**
(percentile of the track's own distribution, never an absolute LUFS/energy cutoff) —
mastering loudness varies too much between tracks for a fixed absolute cutoff to be
meaningful:

```
1. e_thr = percentile(energy_curve, config.hook_high_energy_percentile * 100)
   v_thr = percentile(vocal_band_energy, config.hook_high_vocal_percentile * 100)
   high[i] = energy_curve[i] >= e_thr and vocal_band_energy[i] >= v_thr

2. hook_in = start_time of the first hook_min_bars-wide window where
   mean(high[window]) >= config.hook_plateau_occupancy   # NOT strict
   contiguity — tolerates brief dips (a breath, a quiet fill) inside an
   otherwise-sustained plateau; None if no such window exists.

3. window_end_time = plateau_end_time + bars_to_seconds(config.time_box_bars)
   hook_exit_candidates = [b for b in phrase_grid
                            if plateau_end_time <= b.position < window_end_time]
   — every phrase boundary from the plateau's end up to `time_box_bars` past
   it becomes a candidate `hook_exit`, full stop. No bar-to-bar drop check
   (2026-09-17 amendment — the single-bar delta this step used to require is
   exactly what let a breath between two sung lines pass as "the drop," per
   T7). Bounded, but by an **already-existing** constant — `time_box_bars`
   (§7's "one structural block: intro+buildup+hook," D27's own arithmetic) —
   not a new one: two prior drafts of this window were tried and rejected
   against real tracks before landing here (see `## Amendments`) — an 8-bar
   window found *zero* candidates on one track (the real gap was 27 bars),
   and no bound at all picked a candidate 110 bars past the plateau — 95%
   through a different track — on another. Ranking which candidate *within*
   the window is actually clean is `edge_builder`'s job (spec §4's
   `vocal`/`phrase` cost terms already read the raw per-bar signal at each
   candidate's own position, independent of anything computed here).
   Empty list if the plateau exists but no phrase boundary falls in the
   window (sparse phrasing, or the plateau is near the track's own end).
```

---

## 7. Cue emission (`cues.py`)

Preference orders, from D27/§7.1, cue-kind names per the amended vocabulary (§2):

```
cue_in:   intro / riser_start    — when free_intro_end indicates real DJ padding
                                    (structure_template == "edm")
          hook_in                — when it doesn't (film, genre switch, unknown)
          grid_start              — guaranteed fallback

cue_out:  hook_exit               — preferred, musical (§6). Emitted once per
                                     candidate in `hook_exit_candidates`
                                     (2026-09-17 amendment) — zero, one, or
                                     several `hook_exit` cues per track, all
                                     at the same preference cost; `edge_builder`
                                     picks the winning position, this module
                                     doesn't
          outro_start               — deferred to v2, see `## Amendments` —
                                        unreachable in v1; no detector formula
                                        exists for this branch (unlike hook_exit/
                                        hook_in's §6 formula), and unlike every
                                        other gap resolved in this amendment there
                                        was no real-track data to ground a v1
                                        proposal against. `CueKind.outro_start`
                                        stays in the enum for a future detector;
                                        `cues.py` just never emits it in v1.
          time_boxed                 — guaranteed fallback: first phrase boundary
                                        after `config.time_box_bars` bars from
                                        cue-in, minimizing vocal presence (D22) —
                                        needs only phrase_grid[], which this module
                                        already computes
```

**Cue-in branch 1's exact `CueKind`/position** (see `## Amendments` — this exact
condition wasn't previously stated), reusing the same riser check §3 already makes
rather than re-deriving it:

```
if raw.riser_candidates has a candidate starting before grid_start:
    emit Cue(position=riser_candidates[0].start_time, kind="riser_start")
else:
    emit Cue(position=free_intro_end, kind="intro_end")
    # free_intro_end == grid_start in this branch (no riser present, §3), so
    # this never violates the hard no-cue-before-grid_start constraint below
```

This module emits **every qualifying candidate per side, in preference order** —
not a single winner — so a `riser_start`/`intro_end` cue and the guaranteed
`grid_start`/`first_downbeat` fallback cue can both appear in `cue_ins[]`, even at
the same `position`, when no riser is present. `list[Cue]` (§2) plus the fact that
the (out-of-scope) edge builder needs multiple cue-point combinations to search
across is why this module hands over candidates rather than deciding for it.

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
  exclude_threshold           : float  # default 0.01  (§10 Q2 resolved 2026-08-18,
                                        # see ## Amendments)
  cut_only_threshold             : float  # default 0.15  (§10 Q2 resolved
                                            # 2026-08-18, see ## Amendments)
  edm_intro_bars_threshold          : int  # default 8 (§5)
  hook_high_energy_percentile        : float  # default 0.5 (§6, see ## Amendments)
  hook_high_vocal_percentile          : float  # default 0.5 (§6, see ## Amendments)
  hook_plateau_occupancy                : float  # default 0.7 (§6, see ## Amendments)
  hook_energy_drop_fraction              : float  # default 0.25 (§6, see ## Amendments) —
  hook_vocal_drop_fraction                : float  # default 0.25 (§6, see ## Amendments) —
                                                      # both UNUSED as of the 2026-09-17
                                                      # amendment (§6's per-boundary drop
                                                      # check they fed is gone); kept on the
                                                      # config rather than removed since
                                                      # removing a field is a version bump,
                                                      # not an amendment (README's own rule),
                                                      # and nothing depends on their absence
  phrase_boundary_novelty_std_multiplier   : float  # default 1.0 (§4, see ## Amendments)
  phrase_regularity_cv_threshold             : float  # default 0.3 (§5, see ## Amendments)

derive_cues(raw: RawFeatures, config: CueDerivationConfig) -> CueDerivationResult
  1. grid_start, grid_confidence, free_intro_end = derive_grid_origin(raw)   # §3
  2. phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw, config)   # §4
                                                                    # (config arg
                                                                    # added, see
                                                                    # ## Amendments)
  3. structure_template = classify_structure_template(raw, free_intro_end,
                                                        phrase_grid, config)    # §5
  4. hook_in, hook_exit_candidates = detect_hook(raw, phrase_grid, config)      # §6
                                                     # hook_exit_candidates: list[float],
                                                     # not float | None, since the
                                                     # 2026-09-17 amendment (§6) — hook_in
                                                     # keeps its single-value shape,
                                                     # untouched by that amendment
  5. cue_ins, cue_outs = emit_cues(raw, grid_start, free_intro_end,
                                    structure_template, hook_in, hook_exit_candidates,
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
| Q2 | `exclude_threshold`/`cut_only_threshold` (§8, §9) have no principled default yet — design-v3 §6.5 itself calls the equivalent judgment "currently a hand-tuned heuristic threshold" pending the (v2) grid-confidence model | Needs real tracks run through `feature_extractor` to set sane defaults empirically — **resolved 2026-08-18** against 3 real tracks (see `## Amendments`), then **revisited 2026-08-24 against 69 and found to be the wrong lever**: the thresholds are defensible, but their *input* is mis-scaled, so retuning them would paper over a defect in `feature_extractor` §6. See the 2026-08-24 amendment |
| Q3 | `structure_template`'s two-signal heuristic (§5) hasn't been validated against design-v3's own club-edit vs. film-master test set (D11) | Whether D5's tier-penalty conditioning and D27's cue-kind preference order get the right signal in practice |
| Q4 | Should `hook_exit`/`hook_in` thresholds (§6) vary by `structure_template`, given Bollywood's vocal density is 70-80% (D22) vs. EDM's much lower baseline — does one fixed "significant drop" threshold work for both? | §6's threshold constants — currently assumed template-agnostic |
| Q5 | `hook.py`'s `_bar_index_at` matches a `PhraseBoundary` back to its `per_bar_features` index via exact float equality on `position`/`start_time`, silently skipping the boundary (no error) on any mismatch — safe today only because `detect_hook` is always called with the same `raw`/`phrase_grid` pair `derive.py` just produced in the same call, never a cached or serialized copy (flagged in code review 2026-08-19, deliberately not fixed then: an epsilon-tolerance patch would guard a scenario that can't currently occur, and the real fix — giving `PhraseBoundary` its own `bar_index` field — is a public schema change, i.e. a **new version** of this spec, not a same-day amendment) | Whether `phrase_grid` ever gains a second source (a cached/serialized grid, a future boundary-merge step) — if so, this needs `PhraseBoundary.bar_index` added via a version bump, not another amendment |
| Q6 | ~~`hook_exit`'s drop check (§6) is a single bar-to-bar delta with no sustain requirement...~~ **Resolved and implemented 2026-09-17.** §6 now emits *every* phrase boundary from the plateau's end up to `time_box_bars` past it as a `hook_exit` candidate — no drop check — and `edge_builder`'s existing `vocal`/`phrase` cost terms (§4 of that spec) do the ranking. Two other window designs (8-bar-bounded, fully unbounded) were tried and rejected against real tracks first — see `## Amendments`. Confirmed on the full 15-track gold-set corpus: rendered `MixPlan` averages 80.1s/track (vs. the pre-fix corpus's much wider variance, incl. one track at 95% of its own length) — close to design-v3's ~60–70s/track reference | §6's `hook_exit` formula and every tier-3 cut sourced from it — resolved |
| Q7 | **`hook_in`/`hook_exit` are an energy+vocal-density *proxy* for "the chorus," not real chorus/repetition detection** — they find "a loud, sustained, vocal-heavy passage," which usually coincides with the chorus in verse-chorus pop structure but isn't the same claim, and could misfire on a loud bridge or an extended ad-lib. The actual MIR-correct signal — a full pairwise self-similarity matrix over `RawFeatures.per_bar_features[].chroma_vector` (already computed and cached, 12-dim, Essentia `NNLSChroma`) to find sections that **repeat** later in the track — is explicitly out of scope here (§1's SSM rejection, `overview.md`'s "deliberately not counted as gaps"). Likely why `CueKind.chorus_start`/`chorus_end` exist in the enum (§2) but are never emitted by `cues.py` — probably the intended placeholder for this detector, though nothing in the record confirms that connection; worth confirming before building against it. Deliberately not pursued now — revisit once the full 15-track mix (W3) is audible and it's possible to judge whether the proxy actually misfires often enough to be worth the SSM work | Whether `hook_in`/`hook_exit` need to be replaced (not just Q6-patched) by a repetition-based detector; whether `chorus_start`/`chorus_end` get wired up or pruned from the enum |

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

---

## Amendments

- **2026-09-17 (2)** — **Q6 resolved and implemented: `hook_exit` becomes
  multi-candidate, dropping the per-boundary check entirely.**

  **What changed, §6:** step 3's single `hook_exit = first phrase boundary
  where the drop clears a threshold` becomes `hook_exit_candidates = every
  phrase boundary in [plateau_end_time, plateau_end_time + time_box_bars)`.
  No drop check — `hook_energy_drop_fraction`/`hook_vocal_drop_fraction` (§9)
  go unused (kept on the config rather than removed; removing a field is a
  version bump per the README, not an amendment).

  **Why this over a sustain window** (the fix direction Q6 originally proposed):
  a sustain requirement still commits to a single "best" answer at emission
  time and can fail closed (no candidate at all) if the chorus never has a
  genuinely sustained low-vocal stretch. Handing over every boundary in the
  window and letting `edge_builder`'s already-existing `vocal`/`phrase` cost
  terms (`processing/edge_builder` spec §4) rank them is more robust, and it's
  what `cue_derivation` §7 already claims to do generally ("emits every
  qualifying candidate per side... not a single winner") — `hook_exit`'s old
  formula just never honored that for its own branch. Matches this project's
  standing rule to keep signals soft rather than hard-gated (D10) — no new
  threshold is introduced, an existing one is removed.

  **Two self-corrections during validation, recorded so neither is retried.**
  Both surfaced by actually running this against real tracks before calling
  the fix done — not by reasoning about it in the abstract.

  1. First draft added a *narrow* bounded window (`hook_exit_search_bars`,
     8 bars past `plateau_end_time`), on an unvalidated guess. Checked
     against "Lat Lag Gayee": `plateau_end_time` was `69.03s`, but the
     nearest genuinely clean boundary was `118.12s` — **27 bars later**. The
     8-bar window found **zero** candidates, silently falling back to
     `time_boxed` (which happened to land on the identical position by
     coincidence on this one track — not something to rely on).
  2. Reverted to no bound at all — matching what the old (buggy) algorithm
     actually searched, just without its fragile single-candidate gate.
     Checked against a *different* real track ("Aaj Ki Raat", 297.6s long):
     `edge_builder` picked a `hook_exit` candidate at `283.5s` — **110 bars**
     (95% of the whole track) past `plateau_end_time`. Nothing in
     `edge_builder`'s cost terms penalizes distance from the plateau
     specifically, so an unbounded search can and did pick something nowhere
     near any chorus.
  3. **Landed on reusing `time_box_bars`** (§7's already-existing,
     already-justified "one structural block: intro+buildup+hook ≈ 32 bars,"
     D27's own arithmetic) as the bound, rather than inventing a third
     number. Verified it resolves both prior failures: `69.03 + 32 bars
     (58.75s) = 127.78s` comfortably covers the 27-bar case; `90.86 + 58.75 =
     149.6s` excludes the 110-bar one.

  `hook_exit_search_bars` never shipped, so removing it after step 1 is not
  a version-bump situation — nothing was ever built against it.

  **Confirmed on the full 15-track gold-set** after landing on `time_box_bars`:
  12 of 15 tracks survive quarantine (T1, unrelated to this fix) and render to
  one continuous WAV averaging **80.1s/track** (960.9s / 12 tracks) — close to
  design-v3's ~60–70s/track reference, and a large improvement over the
  window-less-bound run's 107s/track average (one track at 95% of its own
  length). "Lat Lag Gayee" specifically: winning `hook_exit` moved from
  `118.1s` (vocal level `49.8`, T7's original bug) to `96.3s` (vocal level
  `37.5`, energy also drops from ≈−12/−14 to `−17.75` at the same bar — a
  real quiet moment, not a single-bar artifact).

  **`edge_builder` needs no change.** Read directly (`processing/edge_builder/
  build.py`): it already builds its cost cube by iterating `track.cue_outs`/
  `cue_ins` **by index**, computing `cue_kind`/`vocal`/`phrase`/`energy` costs
  per index, then taking an `argmin` over the whole cube — nothing assumes at
  most one cue per kind. It was already built to consume N candidates; this
  amendment is the first time `cue_derivation` actually offers more than one.

  **Contract change, not just an internal detail:** `detect_hook()`'s return
  type changes from `tuple[float | None, float | None]` to `tuple[float |
  None, list[float]]` for the `hook_exit` half (§9's `derive_cues` step 4).
  Treated as an amendment rather than a version bump because `detect_hook` is
  not in this module's exported surface (`__init__.py` exports
  `CueDerivationResult`/`Cue`/`CueKind`/`CueDerivationConfig`/`derive_cues` —
  not `detect_hook`), and `derive_cues`'s own public signature
  (`RawFeatures -> CueDerivationResult`) is unchanged; `CueDerivationResult.
  cue_outs` was always `list[Cue]` and always documented to potentially carry
  several entries per kind (§7). Downstream, `edge_builder` already consumes
  that list by index, so it stays fully compliant with no changes — the
  README's actual test ("does code already implementing the old spec still
  comply?") passes for every real consumer.

  Logged a related but separate open question, **Q7**: `hook_in`/`hook_exit`
  are an energy+vocal-density proxy for "the chorus," not true repetition-based
  chorus detection — `RawFeatures.per_bar_features[].chroma_vector` (already
  cached) is the signal a real self-similarity detector would need, but
  building that is v2 scope (`overview.md`'s "deliberately not counted as
  gaps"), deliberately not pursued now. This amendment doesn't touch that axis
  at all — it only makes the exit point more reliable *within* whatever region
  the existing proxy already identified as the plateau.

- **2026-09-17** — **`hook_exit` false-positive: a single-bar vocal dip mistaken for
  a section boundary (Q6).** Surfaced by ear: rendering a real 2-track `MixPlan`
  (`render_mix`, tier 3 cut-on-the-1) across a `hook_exit`-sourced junction audibly
  cut mid-vocal-phrase.

  **Root cause**, `hook.py`'s `detect_hook()`: the per-boundary check
  (`energy_drop = energy[bar_index-1] - energy[bar_index]`, same for `vocal_drop`)
  is a single bar-to-bar delta against the immediately preceding bar only, with no
  requirement that the drop persists — it takes the *first* `phrase_grid` boundary
  after the plateau that clears `hook_vocal_drop_fraction * (v_high - v_low)`.

  **Confirmed on a real track** — "Lat Lag Gayee" (Race 2, `content_hash
  cb97d0d6…`): the plateau ends at bar 63 (t=116.1s); `hook_exit` fires at the very
  next phrase boundary, bar 64 (t=118.0s). `vocal_band_energy`: bar 63 = `70.07`
  (near the track's own p90, `68.15`), bar 64 = `49.83` — a drop of `20.24`,
  comfortably clearing the threshold (`0.25 × (68.15 − 38.10) ≈ 7.5`) — bar 65 =
  `67.22`, already back near the p90 high-vocal level one bar later. The "drop" that
  triggered `hook_exit` fully reversed within a single bar: ordinary vocal
  micro-dynamics (a breath, the gap between two sung lines — expected given
  Bollywood's 70-80% vocal density, D22/Q4), not an instrumental/outro boundary.

  **Not T1 or T2** (`overview.md`'s open-thread numbering carries over here as T7).
  T1 is `downbeat_confidence` mis-scaling (grid/quarantine); T2 is half-bar phase
  ambiguity. This is a distinct defect in the *drop* half of the `hook_exit`
  formula, independent of both — it fires the same way regardless of grid phase or
  quarantine status.

  **No formula changed in this pass.** The fix direction is a sustain/hysteresis
  requirement — e.g. require `vocal_band_energy` (and/or `energy_curve`) to stay
  below threshold for some number of bars after the boundary, not just the one bar
  immediately after — but the window length and threshold are untuned; recorded as
  Q6 pending that decision.

- **2026-08-24** — **D7 quarantine measured on a real 69-track corpus: it fires on
  86% of the library** (52 `cut_only`, 7 `excluded`, 10 `ok`). Recorded here because
  §8/§9's thresholds are where anyone investigating that number will look first —
  **but they are not the cause, and lowering them is not the fix.**

  §3 sets `grid_confidence = raw.downbeat_confidence`, and that input is mis-scaled:
  `feature_extractor` §6 computes it as the margin between the best and second-best
  bar phase by low-band energy, which in 4/4 music is near-zero precisely when the
  drum programming is *tightest* (beats 1 and 3 both carry kick). Corpus median is
  `0.053` against a `cut_only_threshold` of `0.15`. Tracks with unmistakable bar
  structure score below tracks with none. Full diagnosis, a tested replacement
  metric, and the recorded negative results are in
  `resources/documentation/ingestion/feature_extractor/spec.md`'s 2026-08-24
  amendment and its Q1/Q5.

  **No threshold changed.** Retuning `cut_only_threshold` down to fit the current
  metric's compressed range would restore the track count while keeping the
  quarantine blind to what it is supposed to measure — D7 exists because "a wrong
  beat grid poisons every edge it touches," and a threshold tuned to a broken input
  cannot honour that. If `feature_extractor` §6's metric is replaced, **both**
  thresholds need recalibrating to the new scale in the same pass: the candidate
  replacement's observed floor is `0.027`, above this spec's `exclude_threshold` of
  `0.01`, which would make `status="excluded"` unreachable.

  Q2 above is updated to record that this revisit happened and what it concluded.

- **2026-08-18** — Pre-implementation completion pass: no code exists against this
  spec yet (`overview.md` row 3: Spec Done, Code —), so every change below is
  additive/clarifying (defaults, internal detail — README's amendment column),
  never a public-contract change (`CueDerivationResult`'s schema, `derive_cues`'s
  own signature, and §11's file layout are all untouched). Grounded where possible
  against the three real `RawFeatures` JSONs already committed at
  `src/ingestion/feature_extractor/examples/outputs/*.json` — used as a sanity
  check to catch wrong orders of magnitude and fragile absolute-threshold designs,
  **not** as a fitting/validation set; the exact numbers below are v1 defaults to
  revisit once more real tracks run through the pipeline, not final numbers.
  1. `exclude_threshold`/`cut_only_threshold` (§8, §9, §10 Q2) resolved:
     `0.01`/`0.15`. Measured `downbeat_confidence`: ~0.0015 true-noise floor (no
     phase-differentiating signal at all), 0.013–0.034 across the three real
     tracks, ~0.79 for a confidently phase-locked synthetic case — an order of
     magnitude below what a naive 0–1 "confidence" reading would suggest. Both
     thresholds sit clear of these bands rather than fit to the three exact
     values; all three real tracks land `cut_only`, none `excluded` — consistent
     with tier-3 cut-on-the-1 being film music's designed-for workhorse (D5), not
     a fallback.
  2. Five new `CueDerivationConfig` fields resolve §6's previously-unspecified
     "significant drop" / "sustained high-energy" thresholds:
     `hook_high_energy_percentile=0.5`, `hook_high_vocal_percentile=0.5`,
     `hook_plateau_occupancy=0.7`, `hook_energy_drop_fraction=0.25`,
     `hook_vocal_drop_fraction=0.25`. All per-track-relative (percentile/fraction
     of the track's own p10–p90 range, never an absolute LUFS/energy cutoff) —
     mastering loudness varies too much between tracks (`lufs_integrated` ranged
     −7.5 to −11.4 across the three samples) for a fixed cutoff to be meaningful.
     `hook_plateau_occupancy=0.7` (not strict 100% contiguity) exists because
     strict per-bar contiguity found zero qualifying 8-bar plateaus on 2 of the 3
     real tracks (a single quiet fill/breath breaks the window); occupancy
     tolerance found one on all three. p10/p90 percentile ranges are used instead
     of min/max because one track's `energy_curve` has a single near-silent
     outlier bar (~−300 LUFS) that blows out a min/max-based range by ~30×. §6's
     full formula is now spelled out precisely rather than left as "hand-tuned
     defaults, not derived."
  3. `phrase_boundary_novelty_std_multiplier=1.0` (§4, §9) — `detect_phrase_boundaries`
     previously had no config field for its peak-picking threshold; standard MIR
     peak-picking convention (mean + N·stdev of the novelty curve). §9's
     orchestration step 2 gains a `config` argument to match
     (`detect_phrase_boundaries(raw, config)`).
  4. `phrase_regularity_cv_threshold=0.3` (§5, §9) — the "consistent spacing"
     signal had no numeric cutoff; coefficient of variation (stdev/mean) of
     `bars_since_previous` below this threshold reads "regular." Still explicitly
     unvalidated against D11's test set (§10 Q3 stays open) — this only makes the
     heuristic runnable, not correct.
  5. §5's combination rule completed: previously only "neither signal clears
     confidently → unknown" was stated. The intro-length signal never abstains
     (duration is always known); only the regularity signal can (fewer than 2
     `phrase_grid` gaps). Now: regularity abstains → intro-length's vote; both
     present and agree → that vote; both present and disagree → `"unknown"`.
  6. §7's cue-in branch 1 ("intro/riser_start") given an exact `CueKind`/position
     rule, reusing §3's own riser check rather than re-deriving it: `riser_start`
     at `riser_candidates[0].start_time` when a riser precedes `grid_start`, else
     `intro_end` at `free_intro_end` (which equals `grid_start` in that branch).
     Also stated explicitly: this module emits every qualifying candidate per
     side in preference order, not a single winner — `cue_ins[]`/`cue_outs[]` are
     the full candidate set the (out-of-scope) edge builder searches over, not a
     pre-decided cut point; a preference-order cue and the guaranteed fallback
     cue can both appear, even at the same position.
  7. `outro_start` (§7) declared unreachable in v1 — no section ever defined what
     makes something an outro (unlike `hook_exit`/`hook_in`'s full §6 formula),
     and unlike every other gap here, there was no real-track data to ground a
     v1 detector design against. `cue_out` selection always falls through to
     `hook_exit` or the guaranteed `time_boxed` fallback. `CueKind.outro_start`
     stays in the enum for a future (v2) detector to populate without a schema
     change.
  8. §3 gains an explicit exception for `raw.downbeat_times` being empty — found
     by directly reading `feature_extractor/rhythm.py`: `_detect_downbeats`
     returns `([], 0.0)` under 8 detected beats, so the unmodified formula
     (`raw.downbeat_times[0]`) would raise `IndexError` on exactly the track that
     most needs to quarantine cleanly to `status="excluded"`, since `derive_cues`
     calls `derive_grid_origin` (step 1) before `quarantine` (step 6). Now:
     `grid_start=free_intro_end=0.0`, `grid_confidence=raw.downbeat_confidence`
     (already `0.0` in this case) — flows correctly into `status="excluded"`
     instead of crashing.
