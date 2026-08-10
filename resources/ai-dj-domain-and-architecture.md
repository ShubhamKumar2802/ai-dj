# AI DJ Mixer — Domain Notes & Architecture

Working document. Covers the DJ domain knowledge needed to design the system, the
architectural decisions made so far, and what to build first.

**Target output:** hook-cut Bollywood/English megamix. Reference is ~15 tracks in
~17 minutes (≈60–70s per track), not a long-blend club set.

---

## 1. Domain knowledge

### 1.1 Harmonic mixing (Camelot wheel)

Camelot notation is a DJ-friendly relabelling of the circle of fifths.

- **Number (1–12)** = position on the wheel. Neighbours are a perfect fifth apart
  and share six of seven notes.
- **Letter**: `A` = minor (inner ring), `B` = major (outer ring).

**Free moves from any position:**

| Move | Example | Relationship |
|---|---|---|
| Stay put | 4B → 4B | Same key |
| ±1, same letter | 4B → 3B or 5B | Perfect fifth |
| Same number, flip letter | 4B → 4A | Relative minor/major |

Anything else needs care.

> **Caveat:** key detection on this repertoire is unreliable. Estimators assume
> 12-TET major/minor; raga-influenced or mid-song-modulating film music produces
> confident but meaningless labels. Treat key as a **soft score with a confidence
> value, nullable** — never a hard gate. A strict gate can leave the search with
> no legal successor and dead-end.

### 1.2 Phrasing

The single biggest skill separating "beatmatched" from "mixed".

- 4 beats = 1 bar. Pop and film music is built in 8-, 16-, and 32-bar phrases.
- Sections start on the "1" of a phrase.
- A transition starting mid-phrase sounds wrong **even with perfect beatmatch and
  perfect key**.

### 1.3 Song structure

Intro → verse → pre-chorus → chorus/hook → breakdown → outro.

- Mix **out of** a low-energy region, **into** a low-energy region (outro → intro).
- Never chorus into chorus — two vocal hooks stacked is unlistenable.
- This is why vocal activity detection matters even though stem separation is deferred.

### 1.4 Tempo tolerance

Beyond roughly **±6% stretch**, artifacts become audible and the track's character
changes. Usable neighbours are BPM ± ~6%, not any tempo.

Note: for a hook-cut format, tempo can jump *at a hard cut* — the cut masks it.
This is a degree of freedom a monotonic BPM sort would throw away.

### 1.5 Gain staging

Match perceived loudness between decks before the transition and leave headroom.
Unmatched levels read as "amateur" faster than any harmonic error. Tracks spanning
2001–2013 differ by several dB due to the loudness war — LUFS normalisation is
**required**, not optional.

### 1.6 Transition vocabulary

Ordered by how much information each needs — this doubles as the fallback ladder.

| Tier | Technique | Requires |
|---|---|---|
| 1 | **Bass swap** at detected section boundary | Downbeats, phrase grid, structure, vocal activity |
| 2 | **Bass swap** at nearest confident downbeat on 16-bar grid | Downbeats, phrase grid |
| 3 | **Cut on the 1** — hard switch on a downbeat | One confident downbeat per track |
| 4 | **Echo-out** — beat-synced delay on A, kill A, tail carries into B | Tempo; tolerates bad phase |
| 5 | **Filter fade** — high-pass A up and out over 8 bars | Almost nothing |

**Bass swap** is the core technique: only one bassline at a time. Kill lows on the
incoming track, let its mids/highs sit over the outgoing track's bass, then hand
off. Two full-range tracks overlapping produces comb filtering and low-end pile-up.

**Full crossfade is deliberately absent.** It needs the *most* beat-alignment
accuracy (both tracks audible for a long window) and its failure mode lasts 15
seconds. A bad cut is 100ms of wrongness. The fallback should be the option whose
failure is *brief*, not the one that feels gentlest.

**Tier 3 (cut on the 1) is the workhorse** — robust, and it's the megamix idiom
anyway, so it doesn't read as a failure.

### 1.7 Energy arc

A set builds, peaks, and comes down. Energy dropping mid-set feels like a mistake
even when every individual transition is clean.

Critically: **this is a property of the whole path, not decomposable into pairwise
edge costs.**

---

## 2. Core design decisions

### 2.1 Everything is decided before rendering

```
analysis   audio in, expensive, cached per track, run rarely
planning   metadata only, milliseconds, run constantly
render     audio + plan in, deterministic execution
```

The renderer is dumb — it executes envelopes, it doesn't decide anything.

**Payoff:** replanning is nearly free. Change the target energy curve, set length,
or seed track and regenerate in milliseconds without touching audio. Generate 50
candidate sets, score them, render only the one you like.

### 2.2 The metadata-only invariant

Anything in the planning phase must be testable with small JSON fixtures — no
audio, no large files, millisecond unit tests. **The moment a planning component
needs to peek at a waveform, the design has broken** and every experiment gets
~100× slower.

### 2.3 Ordering is a path search, not a sort

Not "sort by BPM then apply wheel rules." That gives one ordering with no lever to
fix key mismatches, and produces a boring monotonic tempo ramp.

It's a directed graph — nodes are tracks, edge A→B costs a combination of tempo
distance, key distance, energy delta, structure/vocal compatibility, and strategy
tier. You want a minimum-cost path through K of N tracks.

**Not Dijkstra.** There's no target node, and the no-repeats constraint means state
is "which track am I on **and** which have I used" — exponential. This is the
**orienteering problem** (TSP's cousin: pick the best subset, don't visit all).

At N≈30–200, tractable via:

- **Beam search** — keep top ~50 partial sequences, extend, rescore, prune.
  Handles path-level objectives like the energy arc. *Preferred.*
- **Greedy + 2-opt** — fast, but handles path-level objectives badly.

Objective:

```
total = Σ edge_costs + λ · arc_deviation(path) + μ · diversity_penalty(path)
```

### 2.4 Edge cost embeds the junction search

The key insight: whether A→B is a good transition depends on whether a good
transition *point* exists — a phrase-aligned cue-out in A matching a phrase-aligned
cue-in in B with compatible vocal activity. Two tracks can match perfectly on tempo
and key and still have no usable junction.

So ordering and transition-point-finding are **not sequential stages**:

```
for each (A, B):
    best = argmin over (out_i ∈ A.cue_outs,
                        in_j  ∈ B.cue_ins,
                        strategy ∈ tiers)
             of junction_cost(...)
    edge[A][B] = { cost: best.cost, plan: best }
```

**Store the argmin, not just the min** — when path search picks edge A→B, the
transition plan is already computed and comes along for free.

Cost: at N=200, ~8 cue points per side, 5 strategies → 200² × 8 × 8 × 5 ≈ 128M
cheap scalar ops. Seconds in numpy, metadata only.

**Corollary:** transition type selection lives *inside* edge construction, not
after path search. If type is decided after the ordering is fixed, the tier penalty
can no longer influence which pairings get chosen — which was the whole point.

### 2.5 Strategy tier as a cost, not a fallback

The fallback ladder shouldn't be "what do we do when stuck." Adding a per-tier
penalty to the edge cost makes it **"this pairing is worse, pick someone else."**
A tier-4 transition is only accepted when the planner has confirmed nothing better
exists in the pool.

**Log the tier on every transition.** "Percentage of transitions at tier 1 or 2" is
the single best health metric for the analysis pipeline — if it drops when Bollywood
tracks are added, MIR degradation is quantified rather than suspected.

### 2.6 Cache boundary by iteration cost, not by concept

Split analysis where the *iteration cost* changes, not where the concepts differ:

- **Expensive & stable** — decode, beat tracking, downbeats, chroma, LUFS, energy
  envelope. Seconds–minutes per track. Run a handful of times ever.
- **Cheap & volatile** — phrase grid inference, cue point derivation, section
  labelling, confidence gating. Milliseconds. Re-run hundreds of times while tuning.

**Version the cache**, keyed on `(content_hash, feature_extractor_version)` — not
filename. Swapping beat trackers must invalidate stale metadata automatically.
Content hashing also means renames don't trigger re-analysis and duplicates collapse.

### 2.7 Quarantine bad analysis

A track with a wrong beat grid poisons every edge it touches. Every track carries a
`status` — low confidence demotes it to cut-only or excludes it from the pool.
Better a 12-track set that sounds good than a 15-track set with one train wreck.

### 2.8 Scope decision: cue points

Restricting cue points to intros and outros only would produce full-length track
playback — a 60-minute set of 15 complete songs, i.e. the long-blend club set, not
the target format.

**Fix without solving chorus detection:** add a **time-boxed cut** — force a
cue-out at the first phrase boundary after N bars from cue-in. Needs only the
phrase grid. Crude (will sometimes cut mid-chorus) but delivers the format now, and
serves as the baseline a real hook detector must beat.

```
cue_ins  = { intro }
cue_outs = { outro, time_boxed }
```

---

## 3. Architecture

```
                Audio files                          Mix config
                     │                                    │
        ┌────────────┼──────────────────────┐             │
        │  INGESTION │                      │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Feature extractor│  (teal)    │             │
        │   │ beats, downbeats,│            │             │
        │   │ chroma, LUFS     │            │             │
        │   └────────┬─────────┘            │             │
        │            │ RawFeatures          │             │
        │            │ [cached by hash]     │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Cue derivation   │  (purple)  │             │
        │   │ phrase grid,     │            │             │
        │   │ cue ins and outs │            │             │
        │   └────────┬─────────┘            │             │
        └────────────┼──────────────────────┘             │
                     │ Track[]                            │
        ┌────────────┼──────────────────────┐             │
        │ PROCESSING ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Edge builder     │  (purple)  │             │
        │   │ cue pairs ×      │            │             │
        │   │ strategy tiers   │            │             │
        │   └────────┬─────────┘            │             │
        │            │ Scored edges         │             │
        │            ▼                      │             │
        │   ┌──────────────────┐            │             │
        │   │ Path search      │  (purple) ◄┼─────────────┘
        │   │ beam over        │            │
        │   │ partial sets     │            │
        │   └────────┬─────────┘            │
        └────────────┼──────────────────────┘
                     │ MixPlan
        ┌────────────┼──────────────────────┐
        │ EXPORT     ▼                      │
   ────►│   ┌──────────────────┐            │
  audio │   │ Renderer         │  (teal)    │
  bypass│   │ envelopes, gain, │            │
        │   │ stretch          │            │
        │   └────────┬─────────┘            │
        └────────────┼──────────────────────┘
                     ▼
          DJ-mixed playlist track
        + junction preview clips
```

**Teal = touches audio. Purple = metadata only.**

The audio bypass line into the renderer is the load-bearing detail — the plan only
carries sample offsets, so the renderer needs PCM directly. It looks redundant on a
diagram, which is exactly why it keeps getting dropped.

### Where things live (no extra boxes needed)

| Concern | Home |
|---|---|
| Confidence gating / quarantine | Inside cue derivation (a `status` field on `Track`) |
| Transition type selection | Inside edge builder (part of the argmin) |
| LUFS measurement | Feature extractor |
| LUFS **application** | Renderer (target depends on the set, not the track) |
| Playlist serialisation | Output of path search — it's just collecting winning edges |

---

## 4. Data contracts

Write these **before** any DSP code. If they're right, all modules are
independently testable and replaceable.

```
Track:
  id, path, duration, sample_rate
  bpm, bpm_confidence
  beat_times[], downbeat_times[], downbeat_confidence
  phrase_grid[]              # inferred 16/32-bar boundaries
  key, key_confidence        # nullable
  lufs_integrated, true_peak
  energy_curve[]             # per-bar
  cue_ins[]  : { position, kind, confidence }
  cue_outs[] : { position, kind, confidence }
  analysis_version, status
```

```
MixPlan:
  tracks[]
  junctions[]: {
    from, to,
    cue_out, cue_in,
    strategy_tier,
    length_bars,
    gain_db_a, gain_db_b,
    envelopes[]
  }
```

Example junction (bass swap):

```
transition_type: bass_swap
anchor:          downbeat of bar N in track A
length_bars:     16
automation:
  B.low      = kill until bar N+8, then ramp to unity over 4 bars
  A.low      = unity until bar N+8, then ramp to kill over 4 bars
  crossfader = equal-power, bars N..N+12
```

---

## 5. Known risks

| Risk | Notes |
|---|---|
| **Downbeat detection on Bollywood** | Trackers are trained mostly on Western pop/EDM. Tabla/dholak patterns, rubato intros, live orchestration degrade them — especially downbeat *phase*. Beat tracking is largely solved; downbeat phase is not. See CompMusic's work on tala and Indian rhythm analysis. |
| **Key detection validity** | See §1.1. Soft score, nullable. |
| **Large stretch ratios** | 2001–2013 Bollywood spans roughly 90–140 BPM. Phase vocoder vs. Rubber Band artifacts become audible. |
| **Mastering inconsistency** | Loudness-war era spread makes LUFS normalisation mandatory. |
| **Familiarity / nostalgia is not computable from audio** | It's metadata. Good news — fits the metadata-only planner cleanly. Add an explicit familiarity term to the objective. Note it's *audience-relative*, not language-relative. |

### On language-generality

The architecture is language-agnostic — beat grids, chroma, loudness, and section
boundaries don't care. Mixing English and Hindi is fine. What varies is *accuracy*,
per track, not per language.

**Design rule:** make every culturally-loaded assumption a **scored, overridable
input** rather than a hard constraint.

---

## 6. Evaluation

- **Junction preview harness** — render only ±20 seconds around each junction into
  separate files. Reviewing 14 transitions takes 5 minutes instead of sitting
  through a full set.
- **Tier distribution log** — objective signal for analysis pipeline health (§2.5).
- **Human baseline** — feed the planner the same 15-track pool as the reference
  mix and compare orderings. Cheap ground truth.
- **Hand annotation** — mark phrase boundaries, section labels, and cue points for
  5 tracks by ear. One evening's work. This is the ground truth for checking
  whether librosa's structure segmentation is anywhere close.

---

## 7. Build order

### Walking skeleton (first — ~1 day)

Two hard-coded tracks. One cue-out and cue-in found **by ear in Mixxx** and typed
into a JSON file. One hard cut. One rendered WAV. No analysis, no search.

It looks like skipping the interesting part. What it actually does is force the
schema to exist and prove the renderer works, so that when real cue points arrive
they plug into something already functioning. Every subsequent module replaces a
hardcoded value with a computed one, and the system is never broken.

### Then, in order

1. Feature extractor + content-hash cache
2. Cue derivation (intro/outro + time-boxed)
3. Edge builder with tier scoring
4. Path search (beam)
5. Renderer upgrades — bass swap envelopes, LUFS normalisation, time-stretch

### Study path (in parallel, ~2 weeks)

- **3–4 manual mixes in Mixxx** with the actual target playlist, mixing Hindi and
  English. Try the same pair with a 32-bar bass swap, then deliberately start
  mid-phrase — feeling that fail teaches the phrase constraint faster than reading.
  Also try the cut on the 1 and the echo-out.
- **FMP notebooks** (Müller, *Fundamentals of Music Processing*), three chapters
  only: tempo & beat tracking, music structure analysis, chord/key. Run them on
  five of your own tracks. **Where they disagree with your ear is the domain
  knowledge.**
- **Loudness basics** — LUFS, true peak, why R128 exists. One afternoon.
- **Crossfade curves** — equal-power vs. linear, why linear dips. 30 minutes.
- **Mixxx Auto DJ** — it's roughly the baseline the planner must beat. Hearing how
  it fails is a fast way to enumerate constraints.

**Defer:** DSP theory, phase vocoder internals, the ISMIR auto-DJ literature.
Useful *after* hitting the problems they solve.

### Readiness test

You're ready to design when you can write down, in one page, what makes a
transition bad — and each item is something you could compute or approximate.

---

## 8. Tooling

- **Mixxx** — free, open source, no paid tier. macOS 11+ (native on Apple silicon).
  No iOS version. Download from mixxx.org.
  - Does BPM and key detection on the library → free second opinion to compare
    against librosa/Essentia/madmom output. Disagreements are data points.
  - Auto DJ mode = naive baseline.
- **MIR libraries to compare:** `madmom`, `Essentia`, `librosa`. They disagree —
  that's useful.
- **Time-stretch:** Rubber Band vs. phase vocoder.
