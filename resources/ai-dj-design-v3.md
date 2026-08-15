# AI DJ Mixer — Design

**v3 — single source of truth.** Supersedes v1 and v2.

---

## 0. Overview

**Goal:** given a local library, automatically generate and render a DJ mix.

**Format:** hook-cut Bollywood/English megamix — ~15 tracks in ~17 minutes (≈60–70 s
per track). Reference: a Bollywood throwback set by DJ PRIONIC. Explicitly *not* a
long-blend club set; tracks are cut out early rather than played to completion.

**The invariant everything rests on:**

> Analysis extracts metadata from audio. Planning searches over metadata only and
> emits a complete plan. Rendering executes that plan. **Nothing between analysis and
> rendering ever touches a waveform.**

**Labels:** `F1…Fn` empirical findings, `D1…Dn` design decisions. Rejected
alternatives are listed in §12.

---

## 1. Domain reference

### 1.1 Beats, bars, grid

4 beats = 1 bar (4/4). Beat jumps move *beats*, not bars.

> **Never floor a decimal BPM.** 128.4 gridded at 128 puts each beat off by ~1.46 ms
> — ~0.75 s accumulated over four minutes, more than a beat and a half. Aligned at the
> anchor, audibly flamming by the end.
>
> Store BPM as **float**; prefer `beat_times[]` over any scalar. Real recordings drift
> regardless, especially with live musicians.

### 1.2 Harmonic mixing — Camelot wheel

Relabelled circle of fifths. **Number (1–12)** = wheel position; neighbours are a
perfect fifth apart and share six of seven notes. **Letter**: `A` minor, `B` major.

| Move | Example | Relationship |
|---|---|---|
| Stay put | 4B → 4B | Same key |
| ±1, same letter | 4B → 3B / 5B | Perfect fifth |
| Same number, flip letter | 4B → 4A | Relative minor/major |

Avoid the **diagonal** (2A → 3B — changing number and mode at once). "Exactly the same
key" is over-strict and starves the search.

> Estimators assume 12-TET major/minor. Raga-influenced or modulating film music yields
> confident but meaningless labels. Key is a **soft, nullable score with confidence**
> (see D10).

### 1.3 Phrasing

The skill separating "beatmatched" from "mixed". Sections start on the "1" of a
phrase; a transition starting mid-phrase sounds wrong **even with perfect beatmatch
and perfect key**. Phrase *structure* is near-universal in popular music (F1); phrase *length* is not —
Bollywood runs 12 bars where house runs 8 (F8).

### 1.4 Song structure — two templates

**EDM / house** (sections ~16 bars):
`intro → breakdown → build → drop → breakdown → build → drop → outro`

**Bollywood film song** (mukhda / antara):
`intro (long, melodic) → mukhda → antara → mukhda → interlude → antara → mukhda → outro`

**There is no drop.** Cue schemes anchored on "first build, first drop, second build,
second drop" lose half their landmarks.

*Why the difference:* house is produced **for DJs to mix** — 16–32 bars of beatless
material at each end exist purely as blending material. A 2005 film song was mastered
for cinema and radio: cold start, orchestral intro, fade-out. The template is a
production convention, not a fact about music.

**Rules holding across both:**
- Mix **out of** a low-energy region, **into** a low-energy region.
- **Never hook into hook** — two vocal lines stacked is unlistenable. Applies to *both*
  sides of a junction (D22).

### 1.5 Cue templates

| Template | Cue kinds |
|---|---|
| EDM | `track_start`, `intro_8`, `build_1`, `drop_1`, `build_2`, `drop_2`, `outro_start`, `outro_8` |
| Film | `first_downbeat`, `intro_end`, `mukhda_start`, `mukhda_end`, `interlude_start`, `outro_start` |
| Special | `riser_start`, `hook_in` (cue-in only); `hook_exit`, `time_boxed` (cue-out only) |

In the EDM template, cue 1 pairs with 7; cue 2 pairs with 8.

### 1.6 Tempo tolerance

Beyond ~**±6% stretch**, artifacts become audible and character changes. Beat-matching
adjustments must be **gradual, never abrupt**.

Exception: at a hard cut, tempo can jump — the cut masks it. A monotonic BPM sort
throws this degree of freedom away.

### 1.7 Frequency bands and EQ

| Band | Carries |
|---|---|
| Highs | Percussion, hats, white noise |
| Mids | Vocals, instruments |
| Lows | Kick and bass — what you hear from outside a club |

Filter knob: left = low-pass (lows only); right = high-pass (highs only).

> **Cut, don't boost.** Transition EQ prevents frequency clashing, not tone shaping.
> Boosting eats headroom and clips.

### 1.8 Gain staging

Match perceived loudness between decks before transitioning; leave headroom. Unmatched
levels read as "amateur" faster than any harmonic error. 2001–2013 tracks differ by
several dB thanks to the loudness war → **LUFS normalisation is required**.

### 1.9 Transition tiers

Ordered by information required. Doubles as the fallback ladder.

| Tier | Technique | Requires | v1 |
|---|---|---|---|
| 1 | Bass swap at detected section boundary | Downbeats, phrase grid, structure, vocal activity | — |
| 2 | Bass swap at nearest confident downbeat on phrase grid | Downbeats, phrase grid | ✓ |
| 3 | **Cut on the 1** | One confident downbeat per track | ✓ |
| 4 | Echo-out — delay on A, kill A, tail carries into B | Tempo; tolerates bad phase | ✓ |
| 5 | Filter fade — high-pass A up and out over 8 bars | Almost nothing | ✓ |

**Bass swap — the core technique.** Only one bassline at a time; two full-range tracks
overlapping produces comb filtering and low-end pile-up.

1. Cut lows from incoming B; pull down its mids and highs.
2. Bring B in — it sits on A's rhythm bed.
3. At 8 bars (halfway through a 16-bar phrase) **swap basslines**: A's lows off, B's
   lows on. B ≈ 80% volume, A still 100%.
4. Gradually pull A's mids and highs down while raising B to 100% and A to 0.

**Tier 3 is the workhorse** — robust, and the megamix idiom anyway, so it doesn't read
as a failure.

#### Two vocabularies, not one ladder

The tier ordering above encodes *how much analysis a technique needs*, which is not the
same as *how good it sounds*. For material without DJ padding — pop, film masters,
genre switches — tiers 3 and 4 are the **correct professional technique**, not a
degradation. DJ education calls these "emergency" transitions because it is taught from
a house vantage point where every track has a 32-bar intro. §1.4 says that is precisely
what film masters lack, so the emergency case is the normal case here.

| Template | Idiomatic tiers | Penalty shape |
|---|---|---|
| `edm` | 1, 2 preferred | Standard ladder — tiers 3–5 penalised |
| `film` / `unknown` | 3, 4 preferred | Tiers 3–4 carry little or no penalty |

**Film-idiom techniques** (both end by entering B at its hook — see `hook_in`, D27):

| Name | Exit from A | Notes |
|---|---|---|
| **Filtered exit** | At an energy trough, bring lows *and* volume down together over a few bars, then start B | Not a bare cut — needs 2–4 bars of automation. Distinct strategy from tier 3 |
| **Echo-out** | Apply beat-synced delay as the track thins out, kill A, let the tail carry into B | Tail masks alignment error; tolerates poor downbeat phase |

The exit point for both is a **local minimum in `energy_curve[]`** — "where the music
kind of silences down" — the same machinery `hook_exit` uses.

**Full crossfade is excluded.** A crossfader *couples* the channels, so you can't hold
both where you want them; it leaves two kicks and two basslines colliding for the whole
overlap; and it needs the **most** alignment accuracy while failing for 15 seconds.

> **A fallback should be the option whose failure is brief, not the one that feels
> gentlest.** A bad cut is 100 ms of wrongness.

**Higher-level placements** (EDM-structured tracks only, v2):

| Type | Placement |
|---|---|
| 1 | Outro (A) ↔ intro (B) — **the v1 default** |
| 2 | First drop (A) ↔ intro (B) |
| 3 | Drop swap — cue B at its build; crowd expects A's drop, gets B's |

### 1.10 Energy arc

A set builds, peaks, comes down. Energy dropping mid-set feels like a mistake even when
every transition is clean. **This is a property of the whole path — not decomposable
into pairwise edge costs.**

---

## 2. Findings

Observed on this library, in Mixxx.

### F1 — Regular phrasing holds
*Track 1, 2011 Bollywood, ~132 BPM.* Something changes at regular phrase intervals.
Regular phrasing is near-universal in popular music, not an EDM convention — though the
*interval* is 12 bars here, not 8 (F8).

**Why it matters:** the phrase grid is what most of the pipeline runs on. Tiers 2, 3
and the time-boxed cut need only downbeats plus a phrase grid — no structure labels.
That layer generalises even though §1.4's templates do not. → **D8**

### F8 — Bollywood phrases run 12 bars, not 8

*Both sample tracks, by ear.* Phrase boundaries land every **12 bars**, where house
convention is 8 or 16. Meter confirmed as 4/4 — counting in 3 does not feel natural, so
this is not a triple-meter track with a 4/4 grid forced onto it.

> **Meter check worth keeping.** 12 bars of 4/4 = 48 beats, which is *also* 16 bars of
> 3/4 and 8 cycles of a 6-beat tala — 6 and 4 first realign at exactly 48. So a triple-
> meter track with a 4/4 grid wrongly locked onto it presents as "12 bars". Genuine
> 12-bar phrasing costs nothing (D8 absorbs it). A meter mismatch means the **beat grid
> itself is wrong** and every derived value inherits the error. Tap in 3 vs 4 before
> accepting a 12.

**Likely cause:** the mukhda is a 4-line lyrical unit at ~3 bars per line. This is F2
confirmed independently — section lengths follow the **words**, not a production
constraint.

**Design impact: none.** D8 already says detect boundaries, never project them, so a
12-bar phrase is found wherever it is. `phrase_length_bars` was already advisory.

**Impact on defaults, which were tuned for house:**

| Constant | Where | Issue |
|---|---|---|
| `_MIN_PLATEAU_BARS = 8` | `derive/cues.py` | A hook is one 12-bar phrase, so requiring 8 sustained bars means the plateau must fill two-thirds of the phrase before `hook_exit` fires. Try 6 if it under-fires. |
| `length_bars = 16` | `plan/junction.py` | 16 does not divide 12 — a swap starting on a boundary ends 4 bars into the next phrase. Not a bug (the anchor is what matters), but 8 or 12 sits more naturally. |
| `beats_per_bar = 4` | hardcoded in 4 places | Fine for 4/4. If any triple-meter track enters the library, every bar-index computation is wrong by 33%. Add `beats_per_bar` to `RawFeatures` before that happens. |

> **Phrasing is universal; phrase length is not.** Bollywood runs 12 where house runs 8.
> Same shape as every other correction in this document: a house convention taught as a
> fact about music.

→ Confirms **D8**; adjusts defaults only.

### F2 — No global hypermeter
*Track 1.* The bar-16 boundary was clearly stronger than bar 8 — but the pattern did
**not** repeat later in the same track.

Two explanations, both fatal to a projected grid:

1. **Section lengths follow the lyrics.** Mukhda 16 bars, antara 12, interlude 10.
   A strong boundary at 16 means *that section was 16 bars*, not that the track is on a
   16-bar grid.
2. **Metric irregularity.** Two-bar orchestral stabs, tabla fills, a beat of silence
   before the hook returns. Any insertion that isn't a multiple of the phrase length
   **permanently shifts hypermetric phase** for everything after it.

**Diagnostic:** project a strict 8-bar grid from the first downbeat; inspect boundaries
in the final third. Still on grid → irregular section *lengths* (benign). Consistently
offset → metric insertion (dangerous). → **D8**

> Judging "magnitude of change" by ear is unreliable, so part of this may be
> perceptual. The fix holds under either explanation.

### F3 — Unpulsed intros break the grid origin
*Track 2.* No transients in the opening region. Cues from file start matched nothing;
shifting the first cue to the audible beat entry aligned things far better.

Film tracks open with sustained, transient-free material — swells, alaap, drones,
risers. Onset detection has nothing to fire on. Mixxx still *draws* grid lines there,
extrapolated backwards: harmless as display, wrong as cue candidates. → **D9**

**Verifying a hand-placed downbeat:** the first audible hit may be a pickup on beat 4
or a one-off crash. Count 8 bars forward and check something changes. Alignment near
the anchor proves nothing — check the far end (§9).

### F4 — Risers are transition material
*Track 2, zoomed.* Not a static drone: a spectral progression low → mid → high,
resolving in a bright transient at the beat entry. A **riser** — an engineered sweep
built to release on a downbeat.

Risers are *produced against a grid*, almost always 8 or 16 bars. The region is
**metrical but unpulsed**. Layering it over the outgoing track's tail masks alignment
error and builds anticipation.

**Detection is cheap:** monotonic upward drift in spectral centroid terminating in a
transient. No segmentation model. → **D9**, `riser_start`

### F5 — Per-track variance is high
Track 1: clean 8-bar changes. Track 2: unpulsed riser intro, unusable grid origin,
weaker consistency. **Two tracks, two failure modes — uniform assumptions will not
hold.** → **D7**, **D13**

### F6 — Club edits hold the template better, not strictly
Re-produced versions with DJ intros/outros grafted on and tempo locked to a house BPM.
Largely dissolve F2–F4. **They do not eliminate the need for confidence gating.**
→ **D11**

### F7 — Waveform overviews are bar-resolution at best
~830 px for a 4-minute track ≈ 0.29 s/px. At 132 BPM a bar is 1.82 s → **one bar ≈ 6
pixels.** Bar-level structure visible; beat-level precision does not exist at this
scale. → **D15**

---
## 3. Decisions

### D1 — Everything is decided before rendering

```
analysis   audio in · expensive · cached per track · run rarely
planning   metadata only · milliseconds · run constantly
render     audio + plan in · deterministic execution
```

The renderer executes envelopes; it decides nothing.

**Payoff:** replanning is nearly free. Change the energy curve, set length or seed
track and regenerate in milliseconds without touching audio. Generate 50 candidate
sets, score them, render one.

### D2 — The metadata-only invariant

Planning must be testable with small JSON fixtures — no audio, millisecond unit tests.

> **The moment a planning component needs a waveform, the design has broken** and every
> experiment gets ~100× slower.

### D3 — Ordering is a path search, not a sort

A directed graph: nodes are tracks; edge A→B costs tempo distance, key distance, energy
delta, vocal/structure compatibility, and strategy tier. Find a minimum-cost path
through K of N.

**Not Dijkstra** — no target node, and no-repeats makes state "which track am I on *and*
which have I used" (exponential). This is the **orienteering problem**.

```
total = Σ edge_costs
      + λ · arc_deviation(path)
      + μ · diversity_penalty(path)
      + ν · familiarity_score(path)
```

The last three are **path-level**, not decomposable into edges — which is why beam
search (top ~50 partial sequences, extend, rescore, prune) is preferred over greedy +
2-opt. Greedy handles path-level objectives badly.

Termination: **K tracks or pool exhausted** (D21).

### D4 — Edge cost embeds the junction search

Whether A→B is good depends on whether a good transition *point* exists. Two tracks can
match perfectly on tempo and key and still have no usable junction. So ordering and
transition-point-finding are **not sequential stages**:

```
for each (A, B):
    best = argmin over (out_i ∈ A.cue_outs,
                        in_j  ∈ B.cue_ins,
                        strategy ∈ tiers)
             of junction_cost(...)
    edge[A][B] = { cost: best.cost, plan: best }
```

**Store the argmin, not just the min.** When path search picks A→B, the junction plan
comes along free.

Cost at N=200, 8 cue points/side, 5 strategies: ≈128M scalar ops. Seconds in numpy,
metadata only.

**Corollary:** transition *type* is chosen inside edge construction, not after path
search — otherwise the tier penalty cannot influence which pairings get picked.

### D5 — Strategy tier is a cost, not a fallback

A per-tier penalty in the edge cost makes the ladder mean **"this pairing is worse, pick
someone else."** A tier-4 transition is accepted only when nothing better exists in the
pool.

**Health metric — version-specific.** Log the tier on every transition.

> **Condition the metric on `structure_template`.** A low tier-2 share on a film-heavy
> library is *correct*, not unhealthy — tier 3 is the film idiom (§1.9). An unconditioned
> metric tunes against the wrong target and misreads a good mix as a failing one.

| Version | Metric | Note |
|---|---|---|
| **v1, `edm` tracks** | % of transitions at **tier 2** | Tier 1 impossible in v1 (needs structure + vocal activity). Ceiling is lower than it looks. |
| **v1, `film` tracks** | % at **tier 3 or 4 with confident downbeats** | Landing on tier 3 is the goal, not the fallback. Health = downbeat confidence, not tier number. |
| v2 | % at tier 1 or 2 for `edm`; unchanged for `film` | Once structure detection lands |

If the number drops when film masters are added, MIR degradation is quantified rather
than suspected.

### D6 — Cache boundary follows iteration cost

| | Work | Frequency |
|---|---|---|
| **Expensive & stable** | Decode, beat tracking, downbeats, chroma, LUFS, energy | Minutes/track; run rarely |
| **Cheap & volatile** | Boundary detection, cue derivation, vocal mask, gating | Milliseconds; re-run hundreds of times |

**Version the cache** on `(content_hash, feature_extractor_version)` — not filename.
Swapping beat trackers must auto-invalidate. Content hashing also means renames don't
re-analyse and duplicates collapse.

### D7 — Quarantine bad analysis

A wrong beat grid poisons every edge it touches. Every track carries `status`; low
confidence demotes to `cut_only` or `excluded`.

> Better a 12-track set that sounds good than a 15-track set with one train wreck.

Load-bearing because of **F5**.

### D8 — Detect boundaries, never project them

`phrase_length_bars` is **advisory only**. `phrase_grid[]` is a list of *locally
detected* boundaries with novelty scores. Cue derivation prefers high-strength entries;
transitions anchor on detected boundaries only.

**Cost of this rule:** local detection needs a novelty curve good enough to find
boundaries *without* a periodicity prior to lean on. The boundary detector must be
genuinely decent, not merely confirm a grid.

### D9 — Grid origin is the first detected downbeat

Not the file start (**F3**). Cue candidates before `grid_start` are **invalid by
construction** — cue derivation refuses to emit them.

**Two exceptions:**

1. `riser_start` (**F4**) — valid as a cue-in, with the paired constraint that its
   resolution point lands on the outgoing track's phrase boundary. **In v1.**
2. **First track** has no cue-in constraint (D24).

**Airtime budget:** at ~67 s/track, a 15–20 s beatless intro is a quarter of the
track's airtime. Mid-set, `cue_in` is at or after `grid_start` unless a riser is being
used deliberately.

### D10 — Penalties, not filters

> **Every soft musical constraint is a weighted cost term, never a hard gate.**

Applies to key compatibility (§1.2), vocal zones (D22), tempo distance, phrase
strength.

**Why:** with a modest pool and unreliable detection, a strict gate can leave the search
with **no legal successor** and dead-end. Worse, the failure is invisible — you see a
shorter mix, not an error. Penalties give the same output most of the time and degrade
instead of failing.

**The only hard constraints in the system:**

| Constraint | Why hard |
|---|---|
| No track repeats | Definitional |
| Cue positions ≥ `grid_start` | Positions before it are meaningless, not merely bad (D9) |
| `status: excluded` tracks omitted | Analysis is known-broken (D7) |

### D11 — v1 library is club edits, tested against film masters

**F6** says club edits hold the template better, so seed v1 with them.

> **This is library curation, not architecture.** Nothing in the design moves. D7
> already routes low-quality tracks to `cut_only`, so widening the library later costs
> no rework. That reversibility is what makes the narrow scope safe.

> **Preference, not precondition.** `is_club_edit` and `structure_template` are
> per-*track* fields, so this is a scored property gating which cue kinds and tiers
> unlock for that track — D10 applied one level up. A hard library filter would convert
> a preference into a failure mode. Film masters do not fail: no structure labels →
> `time_boxed` cue-out → tier 3 cut, **which is the reference format**. Club edits buy
> tier 2 bass swaps and clean intro/outro pairings — nicer transitions, not a different
> product.
>
> Three practical reasons: Q1 is unanswered, so a hard requirement risks having nothing;
> edit availability skews late (2005–2013), so a filter silently drops the 2001–2003
> nostalgia range that is the emotional core of the reference; and a pure-edit library
> destroys the adversarial test set below.

**Keep 3–5 film masters in the test set** as adversarial cases, or: failure modes stay
hidden, the confidence gate never gets tuned because nothing trips it, and the tier
distribution log has no dynamic range.

### D12 — v1 ships transition type 1 only

> **Two orthogonal axes — do not conflate.**
>
> | Axis | Choices |
> |---|---|
> | What landmarks must be detected | nothing / intro-outro / drops and builds |
> | When you leave a track | play to outro / cut out early |
>
> "Intro→outro only" *sounds* like it forces full-length playback. It does not.
> Bundling them lands you back at a 60-minute set of 15 complete songs.

```
cue_in  = { intro, riser_start, hook_in, grid_start }   # preference order — D27
cue_out = { hook_exit, outro, time_boxed }             # preference order — D27
```

The **time-boxed cut** — first phrase boundary after N bars from cue-in, minimising
vocal presence (D22) — needs only the phrase grid, which type 1 already requires. It is
the guaranteed-to-exist fallback beneath `hook_exit`. Keep `outro`: where a track has a
good one and the budget allows, it's the better exit.

Types 2 and 3 anchor on drops, so they are EDM-specific and may never fire on film
masters. Their ceiling is bounded by how much of the library is club edits.

### D13 — Precision, not accuracy, gates technique unlock

| At 50% | Consequence |
|---|---|
| **Recall** | Fine. Detect drops in half the library, use the technique there, fall back elsewhere. |
| **Precision** | Not fine. Half of drop swaps firing on non-drops is worse than never attempting one. |

The asymmetry is **failure duration**. A drop swap at the wrong point is catastrophic —
16 bars of built anticipation delivering nothing, ~30 s for the listener to notice. A
bass swap slightly off phrase is mildly wrong for a few bars and recovers.

> **For any technique whose failure is long and loud, precision is the gating metric —
> and the detector must know when it is confident.** A detector right 50% of the time
> that *knows which 50%* is usable. One with uniform confidence is not.

### D14 — No model in the planner

The planner is a scoring function over metadata with tunable weights — interpretable,
instantly re-runnable, unit-testable. A model there destroys everything that makes D2
valuable and buys nothing.

### D15 — Vision layer emits proposals, not cue points

Given **F7**, structure detection can never produce a cue position directly:

```
coarse boundary proposal (±1 bar) → snap to phrase_grid → cue candidate
```

Proposal plus refinement. The vision stage need only be roughly right; `phrase_grid[]`
supplies the precision.

### D16 — Pre-rendered output only

The deliverable is a rendered file, not a live player.

Live skipping cannot be served by pre-rendering: if A→B is rendered and the user skips
B, A→C was never built. Supporting arbitrary skips needs the **full N×N matrix** — 900
segments at N=30. Live skipping actually requires **real-time** rendering: audio
callback thread, buffer management, underrun handling, lock-free planner↔audio
communication, streaming time-stretch. A different discipline with a failure mode
(glitches) that does not exist offline.

**This stays a clean seam.** A live player is a **second executor over the same
MixPlan**, not a redesign. Because replanning is nearly free (D1), "skip a track"
becomes "replan and re-render" — seconds for a 17-minute mix.

### D17 — Two renderers, with ramp-aware segment boundaries

```
transition renderer   one junction plan + audio → one segment
playlist renderer     all segments → mix.wav → mp3 + CUE sheet
```

**Segment boundaries.** `ramp_bars` is 0 in v1 and 8 in v2 (D18):

```
blend_start   = junction_start + ramp_bars
blend_end     = blend_start + L

A_body        : A.cue_in       → junction_start
junction      : A[junction_start → blend_end]
                with B[B.cue_in → B.cue_in + L] entering at blend_start
B_body        : B.cue_in + L   → B.cue_out
```

Note A's span (`ramp_bars + L`) and B's span (`L`) differ — B enters after the ramp, not
at `junction_start`.

**Two invariants at every seam:**

1. **Sample-exact boundaries.** No resampling at the join.
2. **Gain continuity.** A discontinuity of a few hundred samples is an audible click.

**Cache junction segments** on `hash(A, cue_out, B, cue_in, strategy, params)`. Tweak
track 12 and junctions 1–11 are untouched.

**Encode last.** Master to WAV; MP3 only as the final step. Never run DSP on lossy
audio. MP3 carries encoder delay and padding — relevant if gapless matters.

**Navigation:** emit a **CUE sheet** (established format, widely understood) plus a
plain timestamp list for a YouTube description.

> **Testability check:** the transition renderer must be callable on a **single junction
> in isolation.** If so, the §9 preview harness comes free. If it needs the whole plan,
> something has leaked.

### D18 — Tempo ramp lives inside the transition segment (v2)

**Invariant: every track plays at native tempo except its own final 8 bars.** The
outgoing track bends to meet the incoming one; the incoming track never bends on
arrival.

**Why beyond smoothness — it decouples a constraint chain.** With one constant rate per
track appearance, a beat-locked junction requires `rate_A × bpm_A = rate_B × bpm_B`. A
mid-mix track has *two* junctions: if the incoming wants 130 and the outgoing wants 134,
that is a contradiction, and tempo assignment becomes a coupled system across the whole
mix. Ramping makes **every junction independently negotiable**.

**Junction-scoped, not track-scoped.** It needs the successor and target rate, so it
cannot be cached per track or run before planning. It is stage 1 inside the transition
renderer:

```
transition_renderer(junction_plan, audio_A, audio_B):
    1. prep   → ramp A's last ramp_bars from bpm_A to bpm_B
    2. blend  → execute the strategy's envelopes
```

Runs only for the ~14 surviving junctions, not all N². During edge building the ramp
cost is pure metadata (`|bpm_A − bpm_B|` per ramp bar), so D2 holds.

| Gotcha | Detail |
|---|---|
| Time-varying rate | Harder than constant. Rubber Band supports it; phase vocoders get finicky. |
| Output duration | An **integral over the varying rate**, not source duration ÷ average rate. Wrong here grid-shifts everything downstream. |
| **Stale beat positions** | After a ramp, beat *k* is no longer at `beat_times_A[k] / rate`. **Prep must emit updated beat positions**, or blend aligns to a stale grid. |
| Audibility | 2–3% over 8 bars (~15 s) is inaudible; 10% is a pitch slide. Extends usable range; does not remove ±6%. |

**Edge cost implication:** tempo distance costs because of **ramp gradient**, not
sustained-stretch artifacts. Penalty on `|bpm_A − bpm_B|` per ramp bar; a longer window
buys tolerance.

**v1 status: not needed.** `ramp_bars = 0`. See D19 for how v1 achieves beat-lock.

### D19 — v1 beat-lock: constant rate, ±3% gate

Without ramping, tier 2's bass swap needs both tracks locked for the blend. v1 applies a
**single constant stretch ratio to the incoming track for its entire appearance**.

> **Tier 2 requires `|bpm_A − bpm_B| / bpm_A ≤ 3%`.** Outside that, tier 2 is unavailable
> for the edge and the planner falls to tier 3 (cut, no lock needed) or tier 5.

3% is tighter than §1.6's ±6% because the stretch is **sustained across the whole track
appearance**, not confined to a transition window. D18 relaxes this in v2.

### D20 — Units: seconds in metadata, samples in the renderer

**All positions in `Track` and `MixPlan` are seconds (float64).** Sample conversion
happens once, inside the renderer, at the canonical rate.

A sample index is meaningless without its rate, and mixing conventions across modules is
silent corruption. This became load-bearing once D25 pinned the rate.

### D21 — No fixed duration target

Beam search terminates on **K tracks or pool exhausted**, not cumulative runtime.

The time-boxed cut is defined in *bars* and bars-to-seconds varies with tempo (32 bars =
58 s at 132 BPM, 77 s at 100 BPM), so track count and runtime don't determine each
other. A duration budget would make path search knapsack-flavoured for an arbitrary
constraint.

**Still log total duration.** 15 tracks landing at 40 minutes against a ~17-minute
reference means the time-boxed cut is mis-sized — a signal, not a constraint.

### D22 — Vocal zones are a heavy penalty on both sides of a junction

§1.4's rule is two-sided: a vocal-free cue-out landing on a vocal cue-in still stacks a
new vocal over the outgoing tail. **Both sides are scored.**

```
vocal_mask[]   # per-bar, energy in 300 Hz – 3 kHz
junction_cost += w_vocal · (vocal_mask[cue_out_bar] + vocal_mask[cue_in_bar])
```

> **Heavy penalty, not a hard gate** (D10). Bollywood film songs are far more vocally
> dense than EDM — often 70–80% vocal — so a hard gate can eliminate **every** cue-out on
> a track, leaving it with no exit and silently dropping it from the pool.

The time-boxed cut becomes: *first phrase boundary after N bars minimising vocal
presence*, which may push it a few bars later — an acceptable trade against cutting
someone off mid-word.

**Proxy caveat:** mid-band energy catches vocals but also strings, brass and lead
synths. **Over-detection is the safe direction.** Superseded in v2 by Demucs vocal-stem
RMS.

### D23 — Energy curve is short-term LUFS per bar

Perceptual; reuses the loudness machinery from §1.8. RMS badly under-weights the low
end, which carries most of the felt energy in this repertoire. The arc scoring in D3
depends on this choice.

### D24 — First and last tracks each have one unconstrained side

| Position | Free side | Behaviour |
|---|---|---|
| 0 | Cue-in | No cue-in constraint — free-time or riser intros are good openers |
| N−1 | Cue-out | Play from `cue_in` to the natural outro and let it end — no time-boxing |

**Fallback for the last track** when no `outro` cue is detected (which will happen —
that's why the time-boxed cut exists): time-box as normal, then apply a 4-bar
equal-power fade to silence.

### D25 — Canonical audio format, pinned at ingestion

**Loudness normalisation and format normalisation are different problems.** Gain
correction addresses *level*; sample rate conversion addresses *speed and pitch*. A
44.1 kHz file decoded as 48 kHz plays ~8.8% fast and ~1.5 semitones sharp — gain does
nothing about that.

**Canonical internal format: 48 kHz, float32, stereo.**

```
sr=48000, mono=False    # explicit at every load site, including the renderer
```

librosa and soundfile resample on load when `sr=` is passed, so this is one parameter
rather than a module. Mono sources upcast to stereo.

> Nasty bug class precisely because the symptom — "something sounds slightly off" —
> does not point at the cause.

### D26 — Normalise all cost terms to [0,1]

Weights (λ, μ, ν, tier penalties, tempo vs key vs energy scale) determine output quality
entirely and cannot be tuned until the eval harness exists. Normalising every term to
`[0,1]` at construction makes weights interpretable as *relative importance* rather than
arbitrary scale factors, shortening the blind period.

### D27 — `hook_exit` and `hook_in`: musical entry and exit

**Problem with time-boxing alone:** "first phrase boundary after N bars" is musically
blind. It lands wherever it lands — possibly two bars into the second antara, possibly
mid-hook.

**What a party set actually wants** is a musical unit: intro → buildup → first mukhda,
exit when the hook resolves. Nobody waits out a full-length film song.

**Cheap approximation from curves already computed.** The first hook is the first
sustained plateau of high energy *and* high vocal presence; its end is where both drop.

```
hook_exit = first phrase boundary where
              energy_curve[] drops significantly
              AND vocal_mask[] drops
            occurring after a sustained high-energy vocal region
            of at least ~8 bars
```

No SSM, no segmentation model — thresholding `energy_curve[]` (D23) and `vocal_mask[]`
(D22) over the per-bar feature stack (§6.3). Roughly a day's work.

#### `hook_in` — the symmetric case

The film-idiom transitions (§1.9) both end with *"start track B from its most
recognisable part."* But `intro`, `grid_start` and `riser_start` all assume B has a
usable intro — which film masters do not have by construction (§1.4).

`hook_in` is the **same detector applied to entry**: the onset of the first sustained
high-energy, high-vocal plateau. One component, both ends of the junction.

This also resolves what D9's airtime note was working around — there is no need to spend
15 seconds getting through a film intro when entry at the hook is available.

#### Preference orders

```
cue_out:  hook_exit    preferred — musical
          outro        when a real outro exists and the budget allows
          time_boxed   guaranteed fallback (instrumentals, odd arrangements)

cue_in:   intro / riser_start    when the track has real DJ padding (edm)
          hook_in                when it does not (film, genre switch)
          grid_start             fallback
```

**The budget and the musical unit coincide.** At 132 BPM a bar is 1.82 s, so a ~67 s
budget is ~36 bars. Intro 8 + buildup 8 + hook 16 = 32 bars ≈ 58 s, plus transition
overlap. This suggests the reference DJ's ~67 s average is a *consequence* of exiting at
the first hook, not a target he set.

**Caveat:** on tracks with a long free-time intro (F3), the intro eats budget without
contributing. D9 already cues in at `grid_start` mid-set, so those tracks start at the
buildup instead — right behaviour, but the shape is not uniform across the library.

---
## 4. Architecture

```
                Audio files                          Mix config
                     │                                    │
        ┌────────────┼──────────────────────┐             │
        │  INGESTION │                      │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Feature extractor│ ◄─ audio   │             │
        │   │ beats, downbeats,│            │             │
        │   │ chroma, LUFS     │            │             │
        │   └────────┬─────────┘            │             │
        │            │ RawFeatures          │             │
        │       ╌╌╌╌╌┼╌╌ CACHE ╌╌╌╌╌╌╌      │             │
        │            │ (content_hash,       │             │
        │            │  extractor_version)  │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Cue derivation   │            │             │
        │   │ phrase grid,     │            │             │
        │   │ vocal mask, cues │            │             │
        │   └────────┬─────────┘            │             │
        └────────────┼──────────────────────┘             │
                     │ Track[]                            │
        ┌────────────┼──────────────────────┐             │
        │ PROCESSING ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Edge builder     │            │             │
        │   │ cue pairs ×      │            │             │
        │   │ strategy tiers   │            │             │
        │   └────────┬─────────┘            │             │
        │            │ ScoredEdges          │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Path search      │ ◄──────────┼─────────────┘
        │   │ beam over        │            │
        │   │ partial sets     │            │
        │   └────────┬─────────┘            │
        └────────────┼──────────────────────┘
                     │ MixPlan
        ┌────────────┼──────────────────────┐
        │ EXPORT     ▼                      │
   ────►│   ┌──────────────────┐            │
  audio │   │ Transition       │            │
  bypass│   │ renderer         │            │
        │   │ (prep) + blend   │            │
        │   └────────┬─────────┘            │
        │            │ segments             │
        │            ▼                      │
   ────►│   ┌──────────────────┐            │
  audio │   │ Playlist         │            │
  bypass│   │ renderer         │            │
        │   │ concat, encode   │            │
        │   └────────┬─────────┘            │
        └────────────┼──────────────────────┘
                     ▼
        mix.wav → mp3 + CUE sheet
        + junction preview clips
```

**Touches audio:** feature extractor, both renderers. **Metadata only:** everything
else.

### 4.1 The audio bypass

The most-dropped detail. MixPlan carries *positions*, not samples — so both renderers
need PCM delivered directly, bypassing the middle layers. It looks redundant on a
diagram, which is exactly why it keeps disappearing.

### 4.2 Where things live — no extra boxes

| Concern | Home |
|---|---|
| Confidence gating / quarantine | Cue derivation — `status` on `Track` (D7) |
| Vocal mask | Cue derivation (D22) |
| Riser detection | Feature extractor — spectral centroid drift (F4) |
| Transition type selection | Edge builder — part of the argmin (D4) |
| LUFS measurement | Feature extractor |
| LUFS **application** | Renderer — target depends on the set, not the track |
| Tempo ramp (prep) | Transition renderer stage 1 — junction-scoped (D18) |
| Segment caching | Transition renderer (D17) |
| MP3 encoding | Playlist renderer, final step (D17) |
| Playlist serialisation | Output of path search — collecting winning edges |

Name arrows by artifact: `RawFeatures` → `Track[]` → `ScoredEdges` → `MixPlan`.

---

## 5. Data contracts

Write these **before** any DSP code.

> **All positions are seconds (float64)** (D20). Sample conversion happens once, in the
> renderer, at 48 kHz (D25).

### 5.1 Track

```
Track:
  id, path, content_hash, duration
  sample_rate                    # canonical 48000 (D25)

  # tempo (§1.1)
  bpm, bpm_confidence            # FLOAT, never floored
  beat_times[], downbeat_times[]
  downbeat_confidence

  # grid origin (D9 / F3)
  grid_start, grid_confidence    # grid undefined before grid_start
  free_intro_end

  # phrasing (D8 / F2)
  phrase_length_bars             # ADVISORY ONLY — do not project
  phrase_grid[] : { position, strength, bars_since_previous }

  # harmony (§1.2)
  key, key_confidence            # nullable

  # loudness (§1.8)
  lufs_integrated, true_peak

  # energy + vocals
  energy_curve[]                 # short-term LUFS per bar (D23)
  vocal_mask[]                   # per-bar 300Hz-3kHz energy (D22)

  # structure
  structure_template             # "edm" | "film" | "unknown"

  # cues (§1.5)
  cue_ins[]  : { position, kind, confidence }
  cue_outs[] : { position, kind, confidence }

  # LLM-derived metadata (§6)
  familiarity_score, era, is_club_edit

  analysis_version
  status                         # ok | cut_only | excluded
```

Cue positions before `grid_start` are invalid and must not be emitted, except at mix
position 0 (D24).

### 5.2 MixPlan

```
MixPlan:
  config : { track_count, energy_arc, seed_track, tier_penalties, weights }
  tracks[]
  junctions[] : {
    from, to,
    cue_out, cue_in,             # seconds
    strategy_tier,
    ramp_bars,                   # 0 in v1 (D18/D19)
    length_bars,
    rate_a, rate_b,              # constant stretch ratios (D19)
    gain_db_a, gain_db_b,
    envelopes[]
  }
```

**Example junction — bass swap:**

```
strategy_tier: 2
anchor:        downbeat of bar N in track A
ramp_bars:     0
length_bars:   16
automation:
  B.low      = kill until bar N+8, then ramp to unity over 4 bars
  A.low      = unity until bar N+8, then ramp to kill over 4 bars
  crossfader = equal-power, bars N..N+12
```

---

## 6. ML strategy

**Almost nothing here needs training.** Most components are classical DSP or pretrained
models off the shelf.

| Module | Approach | Train? |
|---|---|---|
| Beat / downbeat tracking | Pretrained (madmom RNN+DBN, or current SOTA) | No |
| Chroma, spectral features, LUFS | Classical DSP | No |
| Key estimation | Chroma template matching, or pretrained | No |
| Riser detection | Spectral centroid drift + transient (F4) | No |
| Vocal mask (v1) | 300 Hz–3 kHz band energy (D22) | No |
| Vocal activity (v2) | Demucs/HTDemucs offline → vocal-stem RMS | No — pretrained |
| Phrase boundary detection | Foote checkerboard on per-bar features | Maybe, small |
| Section labelling | SSM + clustering, unsupervised | Maybe, small |
| **Grid confidence calibration** | Small supervised model | **Yes — highest value** |
| Edge cost / path search / renderer | Deterministic | Never (D14) |

### 6.1 Where an LLM belongs

**Familiarity and nostalgia scoring.** Not computable from audio — it is world
knowledge. Feed title, film, year, artist; get back era, recognisability, party-
appropriateness, whether it's a club edit. One call per track, cached forever, pure
metadata (D2 holds). Enters the objective as the path-level `ν` term (D3). It is
**audience-relative**, not language-relative.

Secondary: parsing natural-language mix config. Interface sugar.

That is the complete list. Everything else is dense localisation over continuous
signals, which LLMs are structurally bad at.

### 6.2 Not a VLM, not a 7B

**VLM:** inherits the D15 problem (modelling rendered pixels instead of the feature
array) and adds a worse one — VLMs are poor at precise spatial localisation. You need
bar-level boundaries; you'd get "somewhere in the middle."

**Fine-tuned 7B:** wrong inductive bias (boundary detection over `n_bars × d` is
translation-equivariant local pattern matching — a 1D CNN/TCN at ~100–500K params will
*beat* it); not enough data (20–50 annotated tracks); and 7B inference per track on top
of minutes-long feature extraction is a real tax for a worse result.

**Legitimate middle path:** transfer from a music representation model (MERT, CLAP-style
embeddings) as a **frozen feature extractor with a small trained head**.

### 6.3 Structure detection

**Two halves, weeks apart in effort.** *Segmentation* — where boundaries are — is cheap
and **in v1**. *Labelling* — what each section is — needs repetition analysis and stays
v2. `hook_exit` (D27) needs only the first: you don't need to know a section is called a
mukhda, only that energy and vocals plateaued then dropped.

> **Model the feature array, not the rendered image.** The waveform overview is a lossy
> re-encoding of data already held at higher fidelity. Keep the framing (2D, edges,
> blocks, repetition). Drop the pixels.

#### Step 1 — per-bar feature stack (v1)

What the eye reads in a waveform is directly computable: texture density → spectral
flux; colour shift → spectral centroid; height → RMS.

```
per_bar: [ rms, spectral_centroid, spectral_flux,
           low_band_energy, high_band_energy, chroma_vector ]
```

An `n_bars × d` array; boundary detection on it is a **1D problem**.

**One component, three consumers:** the D8 novelty curve, D27's `hook_exit`, and
boundary proposals. Three of the six features already exist. This is why it moved out of
v2 — it was being leaned on from three directions.

> **Model the feature array, not the rendered image.** The waveform overview is a lossy
> re-encoding of data already held at higher fidelity. Keep the framing (2D, edges,
> blocks, repetition). Drop the pixels.

#### Step 2 — template-constrained decoding (v2)

Not free boundary detection. The templates in §1.4 give **order, not position** — F2
showed film section lengths follow the lyrics, so durations are a distribution, not a
constant. But the *sequence* is predictable: intro precedes mukhda, antara follows
mukhda, mukhda recurs.

```
observations: per-bar features
prior:        label grammar + per-label duration distributions
decode:       Viterbi over the label sequence
```

**Why this beats free detection:** it converts a false-positive problem into a parsing
problem. Free detection fires on every loud moment; constrained decoding can only place
a boundary where the grammar permits — so precision rises sharply, which D13 says is the
gating metric. **No training required:** an HMM with hand-set priors, tuned against
annotated tracks.

This is strongest exactly where D11 aims v1: club edits are house-structured with real
16-bar sections, because that regularity is a production constraint. On film masters it
degrades to order-only.

> **D10 again — template fitting always produces a parse.** Force the EDM grammar onto a
> track without that structure and you get confident, wrong labels. Score the fit; low
> fit confidence falls back to free segmentation for `hook_exit`, then `time_boxed`.
>
> Corollary: `structure_template` is not classified up front and trusted. Try both
> grammars, take the better-scoring parse, keep the score.

**Step 3 — SSM for repetition (v2).** Off-diagonal stripes reveal that bars 33–48 are
the same material as 97–112 — invisible in a waveform. Baseline: Foote's **checkerboard
kernel** along the diagonal. Buys "identify the *best* hook of several" rather than
"identify where a hook ends" — a real upgrade, not on the critical path.

Output is **proposals**, not cue points (D15).

### 6.4 Labels come free

Every track prepped by hand in Mixxx is annotated ground truth. Mixxx stores its library
in a **local SQLite database with a cues table**, so positions can be exported
programmatically (confirm schema — Q2). ~20 tracks over a few evenings → a real eval set
produced as a side effect of learning to mix.

> **Cues must span the full track duration.** Early sessions clustered them in the first
> ~10% — fine for investigating grid origin, useless as training data.

### 6.5 If you train one thing

A **grid confidence estimator**, not a structure detector.

```
input:  DBN posterior, tempo stability, onset density,
        spectral flatness in intro, beat-interval variance
output: P(beat grid is correct)
```

- **Cheap labels:** binary per track — "did the grid look right in Mixxx?" 100 tracks in
  an evening. A structure detector needs boundary-level annotation on every track.
- **Feeds the load-bearing mechanism:** D7 quarantine and D13's precision gate both need
  to know when analysis is trustworthy. Currently a hand-tuned heuristic threshold.
- **General unlock:** every later technique gates on calibrated confidence.

Logistic regression or gradient boosting over a dozen engineered features is likely
enough. A small tabular problem, not a deep learning one.

---
## 7. Scope

### 7.1 v1

| Dimension | Decision | Ref |
|---|---|---|
| Library | Mixed; club edits preferred via scoring, film masters degrade to tier 3 | D11 |
| Transitions | Type 1 only (outro ↔ intro) | D12 |
| Cue-ins | `intro`, `riser_start`, `hook_in`, `grid_start` (preference order) | D9, D12, D27 |
| Cue-outs | `hook_exit`, `outro`, `time_boxed` (preference order) | D12, D27 |
| Strategy tiers | 2 (gated at ±3%), 3, 4, 5 — penalties conditioned on template | D19, §1.9 |
| Filtered exit | Lows + volume down at an energy trough, then B at its hook | §1.9 |
| Beat-lock | Constant rate on incoming track; `ramp_bars = 0` | D19 |
| Vocal handling | Band-energy proxy, heavy penalty both sides | D22 |
| Segmentation | Per-bar feature stack; boundaries + `hook_exit` | §6.3, D27 |
| Section labelling | None — `hook_exit` needs boundaries, not labels | §6.3 |
| Duration target | None — terminate on K tracks | D21 |
| Audio format | 48 kHz float32 stereo, pinned at ingestion | D25 |
| ML | None trained; pretrained beat tracker + LLM familiarity | §6 |
| Output | mix.wav → mp3 + CUE sheet + junction previews | D17 |

### 7.2 v2

| Feature | Unlocks | Gated on |
|---|---|---|
| Tempo ramping, `ramp_bars = 8` | Wider tempo range for tier 2; longer blends | D18 |
| Demucs vocal stems | Tier 1; replaces the D22 proxy | Precision (D13) |
| Template-constrained decoding | Section labels; higher-precision boundaries | Precision (D13) |
| SSM repetition | Best-hook selection rather than first-hook | Precision (D13) |
| Drop / build detection | Transition types 2 and 3 | Precision (D13) |
| Grid confidence model | Calibrated D7 gating | §6.5 |
| Real-time playback | Live skip | Second executor over MixPlan (D16) |

---

## 8. Risks

| Risk | Notes | Ref |
|---|---|---|
| **Downbeat detection on film music** | Trackers are trained mostly on Western pop/EDM. Tabla/dholak patterns, rubato intros, live orchestration degrade them — especially downbeat *phase*. Beat tracking is largely solved; downbeat phase is not. See CompMusic on tala. | §1.1 |
| **Unpulsed intros** | Transient-free openings give onset detection nothing to fire on; grids anchored at file start are meaningless. | F3, D9 |
| **Meter mismatch** | 48 beats reads as "12 bars of 4/4" but is equally 16 bars of 3/4 or 8 cycles of a 6-beat tala. A tracker forcing 4/4 onto triple meter produces a wrong grid, not just a wrong phrase length. Tap in 3 before accepting a 12. | F8 |
| **House-tuned defaults** | Plateau minimums, junction lengths and `beats_per_bar` are all house numbers. They are defaults, not design — revisit against 12-bar phrasing. | F8 |
| **Hypermetric phase drift** | Odd-length fills permanently shift phrase phase mid-track; a projected grid silently desynchronises. | F2, D8 |
| **Per-track variance** | Two tracks, two failure modes. Confidence gating is load-bearing, not optional. | F5, D7 |
| **Structure model mismatch** | DJ education teaches the EDM template; film music has no drop. Cue schemes anchored on drops silently fail on half the library. | §1.4 |
| **Melodic intros/outros** | The EDM shortcut "intros are percussion-only so key doesn't matter" does **not** hold for film songs. Key matters across *more* of the track. | §1.4 |
| **Key detection validity** | Estimators assume 12-TET major/minor. Soft, nullable. | §1.2, D10 |
| **Vocal density** | Bollywood is 70–80% vocal; any hard vocal gate empties the cue set silently. | D22, D10 |
| **BPM rounding drift** | Flooring accumulates ~0.75 s over four minutes. | §1.1 |
| **Sample rate / channel mismatch** | 44.1 kHz decoded as 48 kHz plays 8.8% fast. Loudness normalisation does not fix it; symptom is vague. | D25 |
| **Sustained stretch on incoming track** | v1 stretches the incoming track for its whole appearance, so tolerance is ±3%, not ±6%. | D19 |
| **Variable tempo** | Tracks not recorded to a click cannot be described by a scalar BPM; time-stretch must follow `beat_times[]`. | §9 |
| **Mastering inconsistency** | Loudness-war spread makes LUFS normalisation mandatory. | §1.8 |
| **Untunable weights** | Output quality rests on weights that cannot be tuned until the harness exists. | D26 |
| **Club edit sourcing** | Edits circulate via DJ pools and SoundCloud, not commercial stores. If no legal local supply exists, D11 reverses. | D11, Q1 |

**On language-generality.** The architecture is language-agnostic — beat grids, chroma,
loudness and boundaries don't care. What varies is *accuracy*, per track, not per
language.

> **Make every culturally-loaded assumption a scored, overridable input rather than a
> hard constraint** (D10).

---

## 9. Evaluation

### Subjective

**Junction preview harness.** Render ±20 s around each junction into separate files.
Reviewing 14 transitions takes 5 minutes instead of sitting through a full set. This is
the feedback loop that makes everything else improvable — and it falls out of D17 free.

**Human baseline.** Feed the planner the same pool as the reference mix and compare
orderings.

### Objective

- **Tier distribution** — % at tier 2 in v1 (D5). Best single health metric.
- **Total duration** — logged, not constrained (D21). Way off the reference means the
  time-boxed cut is mis-sized.
- **Excluded/cut_only counts** — how often D7 fires, and on what.

### Diagnostics across the library

| Test | Method | Tells you |
|---|---|---|
| **Grid projection** | Project a strict 8-bar grid from the first downbeat; inspect the final third | How much local detection is doing vs what projection could handle (F2) |
| **Tempo stability** | Anchor on the first real downbeat, skip to the last 30 s, check markers still sit on the kick | Aligned → hypermetric irregularity. Drifted → variable tempo, harder renderer (F3) |
| **Club edit audit** | Does the track open/close with 16–32 bars of beatless material, or start cold and fade? | How often `structure_template` = `edm`; whether film-structure work is v1 or v2 (F6) |
| **Hand annotation** | Mark boundaries, sections, cues for 5–20 tracks | Ground truth for whether classical segmentation is close enough (§6.4) |

---

## 10. Build order

### Walking skeleton — first, ~1 day

Two hard-coded tracks. One cue-out and cue-in found **by ear in Mixxx**, typed into
JSON. One hard cut. One rendered WAV. No analysis, no search.

> It looks like skipping the interesting part. What it does is force the schema to exist
> and prove the renderer works, so real cue points plug into something already
> functioning. Every subsequent module replaces a hardcoded value with a computed one,
> and the system is never broken.

### Then

1. Feature extractor + content-hash cache (D6, D25)
2. Per-bar feature stack — energy curve, vocal mask, novelty (§6.3 step 1)
3. Cue derivation — `grid_start`, intro/outro, `hook_exit`, time-boxed cut
   (D9, D12, D22, D27)
4. Edge builder with tier scoring (D4, D5, D19)
5. Path search — beam (D3)
6. Transition renderer — bass swap envelopes, LUFS, constant-rate stretch (D17)
7. Playlist renderer — concat, WAV master, MP3, CUE sheet (D17)
8. LLM familiarity scoring (§6.1)

### Study path, in parallel — ~2 weeks

- **3–4 manual mixes in Mixxx** with the target playlist, Hindi and English. Try a
  32-bar bass swap, then deliberately start mid-phrase — feeling that fail teaches the
  phrase constraint faster than reading. Also try the cut on the 1 and the echo-out.
- **FMP notebooks** (Müller), three chapters: tempo & beat tracking, structure analysis,
  chord/key. Run them on five of your own tracks. **Where they disagree with your ear is
  the domain knowledge.**
- **Loudness basics** — LUFS, true peak, R128. One afternoon.
- **Crossfade curves** — equal-power vs linear. 30 minutes.
- **Mixxx Auto DJ** — roughly the baseline to beat; hearing how it fails enumerates
  constraints.

Defer: DSP theory, phase vocoder internals, ISMIR auto-DJ literature.

> **Readiness test:** you are ready to design when you can write down, in one page, what
> makes a transition bad — and each item is something you could compute or approximate.

---

## 11. Tooling

| Tool | Role |
|---|---|
| **Mixxx** | Free, open source, macOS 11+ native on Apple silicon (no iOS). Manual practice, second-opinion BPM/key, Auto DJ baseline, SQLite cues table as label source. |
| `madmom` | Beat and downbeat tracking |
| `Essentia`, `librosa` | Features, key, segmentation |
| Demucs / HTDemucs | Stem separation (v2) |
| Rubber Band | Time-stretch — constant rate v1, time-varying v2 |

They disagree with each other; the disagreement is a data point.

**Key detection:** Mixed In Key is the industry standard but is paid, desktop-only, and
has **no developer API**. **KeyFinder** (free, open source) is the usable equivalent,
tuned for electronic music so it carries the same 12-TET problem. There is no good
public catalogue API for track keys — detection runs locally.

---

## 12. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Is a legal local supply of Bollywood club edits available? | D11 — if not, it reverses and film-master handling is v1 work |
| Q2 | Mixxx SQLite schema — exact table/column names for cues | §6.4 label export |
| Q3 | Track 2: hypermetric irregularity or variable tempo? | Renderer complexity (§9 tempo stability test) |
| Q4 | Are the reference mix's tracks club edits or film masters? | Calibrates expectations for the whole approach |
| Q5 | Does Mixxx's 132.00 / 0.00 mean genuinely identical tempo, or a snapped 131.8? | Whether the tooling has the §1.1 flooring problem |
| Q6 | Current SOTA beat/downbeat tracker — is madmom still default? | Feature extractor choice |
| Q7 | Does Rubber Band's time-varying mode hold quality across a 3% ramp over 8 bars? | D18 viability |
| Q8 | Is gapless playback required for the target channel? | MP3 encoder delay/padding handling (D17) |
| Q9 | Does 12-bar phrasing hold across the library, or is it per-track? | Whether `_MIN_PLATEAU_BARS` and `length_bars` become per-track or stay constants (F8) |
| Q10 | Any triple-meter tracks in the library? | Whether `beats_per_bar` must enter `RawFeatures` now (F8) |

---

## 13. Rejected alternatives

Kept so they are not re-litigated.

| Rejected | Instead | Why |
|---|---|---|
| Sort tracks by BPM, then apply wheel rules | Path search (D3) | One ordering with no lever to fix key mismatches, and a monotonic tempo ramp is boring |
| Choose transition type after path search | Type inside edge construction (D4) | Tier penalty can't influence pairing choice if the ordering is already fixed |
| Full crossfade as universal fallback | Tier ladder (§1.9) | Needs the *most* alignment accuracy and fails for 15 s; playing to the end defeats the format |
| Infer `phrase_length_bars` and project a global grid | Detect boundaries locally (D8) | Section lengths follow lyrics; odd-length insertions shift phase permanently (F2) |
| Discard free-time intros as dead airtime | Riser cue-in (D9) | The region was a riser — metrical, grid-aligned, and the best transition material available (F4) |
| Hard key gate ("exactly the same key") | Penalty (D10) | Starves the search; can dead-end with no legal successor |
| Hard vocal gate on cue-out | Two-sided penalty (D22) | Bollywood is 70–80% vocal — a hard gate empties the cue set and silently drops the track |
| Gradual beat-match as a stage before rendering | Ramp inside the junction (D18) | As an upstream stage it stretches A's tail, so A's body can't render without knowing the successor |
| Live playback assembling pre-rendered segments | Pre-rendered mix (D16) | A skip invalidates the junction; arbitrary skips need the full N×N matrix. Live skip actually requires real-time DSP |
| Fixed total-duration target | K tracks (D21) | Bars-to-seconds varies with tempo, so count and runtime don't determine each other; makes search knapsack-flavoured for an arbitrary constraint |
| Restrict the library to club edits only | Per-track scoring (D11) | Film masters degrade to tier 3 cuts, which *is* the reference format. A hard filter risks Q1 leaving nothing, silently drops the 2001–2003 nostalgia range, and destroys the adversarial test set |
| A single tier ladder for all material | Two vocabularies, penalties conditioned on `structure_template` (§1.9) | The ladder encodes *analysis required*, not *quality*. Tiers 3–4 are the correct idiom for film masters, so a flat penalty pushes the planner away from the right answer |
| Cue-ins assuming every track has a usable intro | `hook_in` (D27) | Film masters have no DJ padding by construction; `intro`/`riser_start` do not exist for them |
| Time-boxed cut as the only cue-out | `hook_exit` preferred (D27) | N bars is musically blind; lands mid-hook or two bars into the second antara |
| "Loudness normalisation covers format normalisation" | Canonical format (D25) | Unrelated problems — gain addresses level, resampling addresses speed and pitch |
