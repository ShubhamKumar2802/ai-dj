# Transition Renderer — Spec

**Layer:** `render/` — first module in this layer, alongside `playlist_renderer`.
**Implementation staged in two milestones** (§4): Milestone A (tier 3, walking
skeleton) now; Milestone B (tiers 2/4/5, tempo lock) once edge builder + path search
exist. This spec covers the full D17 design so Milestone B is an amendment, not a
rewrite.

---

## 0. Invariant

> **`render_junction` is callable on a single junction in isolation** — one
> `Junction` plus the two tracks' PCM in, one rendered segment out. It has no
> dependency on a full `MixPlan`, a mix position, or any other junction.

This is design-v3 D17's own testability check, stated as this module's reason for
being organized the way it is: it's what makes §9's junction-preview harness (render
±20s around any junction, review 14 transitions in 5 minutes) free rather than a
separate thing to build — and it's exactly what lets the walking skeleton call this
module directly with a hand-typed `Junction`, with no `edge_builder`/`path_search`
in the loop at all (design-v3 §10).

---

## 1. Scope & consumers

**Boundary:** audio-touching (§4: "Touches audio: feature extractor, both
renderers"), deterministic — given the same `Junction` and PCM, always produces the
same output. Decides nothing (D1: "the renderer executes envelopes; it decides
nothing") — every automation curve, gain value, and stretch ratio it applies comes
from the `Junction` it's handed, never computed here.

**Consumer:** `playlist_renderer` (separate spec) — concatenates this module's
per-junction segments plus the leading/trailing track bodies into the full mix.

**Out of scope:** choosing a strategy tier (that's edge-builder's job, part of the
D4 argmin, not yet specced), choosing cue points (`cue_derivation`, already specced),
computing gain targets from LUFS (`playlist_renderer`'s concern per §4.2: "LUFS
application — Renderer — target depends on the set, not the track").

---

## 2. Data contracts (`schema.py`)

```
StereoPCM:
  samples      : np.ndarray   # shape (n_samples, 2), float32 — channels-last,
                               # matching ingestion/feature_extractor/loader.py's
                               # own StereoPCM and soundfile's frame-major layout
                               # (see Amendments 2026-08-29)
  sample_rate  : int          # must be 48000 (D25) — carried explicitly on the
                               # value itself, not assumed by the caller; every
                               # function in this module asserts it rather than
                               # trusting the field silently
```

**`Junction` and `Envelope` are imported from `common/contracts/schema.py`**, not
defined here — `schema.py` re-exports them so this module's public surface is
unchanged. Their field lists live in
`resources/documentation/processing/edge_builder/spec.md` §2, which is now their
single owner.

They were originally defined here, with `playlist_renderer` importing them ("one
contract, one owner"). That ownership predated `processing/edge_builder`, which is
what actually *produces* a `Junction` — leaving the contract in `render/` would have
made the planning layer depend on the render layer, and moving it into `processing/`
would only have inverted the same problem. A neutral shared location leaves neither
layer depending on the other. Nothing about the fields changed in the move.

`StereoPCM` stays here: it is audio-only and never crosses into planning.

---

## 3. Segment boundary math (D17)

General formula (D17, §5.2):

```
blend_start = junction_start + ramp_bars
blend_end   = blend_start + length_bars

A_body   : A.cue_in → junction_start
junction : A[junction_start → blend_end] with B[B.cue_in → B.cue_in + L] entering
           at blend_start
B_body   : B.cue_in + L → B.cue_out
```

**Bars to seconds to samples.** `ramp_bars` and `length_bars` are counts of *bars*,
as are every `Envelope` breakpoint's `bar_offset`. `Junction.bar_seconds`
(`edge_builder` spec v2 §6) is the conversion factor — track A's bar length, since
the window is anchored on A's exit:

```
seconds  = n_bars * junction.bar_seconds
samples  = round(seconds * SAMPLE_RATE)          # 48000, D25 — once, here
```

Nothing else on the `Junction` carries tempo, and `StrategyFn` (§4) receives no
other input, so this field is the only thing that makes any `length_bars > 0` tier
renderable at all (see `## Amendments`).

**Tier 3 degenerates this to zero length.** With `ramp_bars = 0` and
`length_bars = 0`: `junction_start = blend_start = blend_end = cue_out`. There is no
blend region — `render_junction` for tier 3 is exactly:

```
output = fade_out(A.samples[A_start : cue_out], FADE_MS) ++ fade_in(B.samples[cue_in : B_end], FADE_MS)
```

where `A_start = 0` in Milestone A — the opener plays from the top of its file (see
Amendments 2026-08-29 and §5). A literal splice, not a blend — the two fades below
don't overlap (§4's anti-click treatment is not a tier-2-style crossfade wearing a
different name).

**Two invariants that apply even to this degenerate case** (D17):

1. **Sample-exact boundaries** — `cue_out`/`cue_in` (seconds, float64, D20) convert
   to sample indices once, at this module's canonical rate (48000, D25); no
   resampling at the join.
2. **Gain continuity** — a discontinuity of more than a few hundred samples at the
   seam is an audible click. Tier 3 satisfies this via the anti-click fade (§4), not
   via gain matching (that needs LUFS data this module never receives).

---

## 4. Strategy dispatch (`strategies/`)

A registry keyed on `strategy_tier`, mirroring the provider-registry pattern already
established in this repo
(`resources/documentation/common/llm_service/spec.md` §6):

```
StrategyFn = Callable[[Junction, StereoPCM, StereoPCM], StereoPCM]

register_strategy(tier: int, fn: StrategyFn, *, overwrite: bool = False) -> None
get_strategy(tier: int) -> StrategyFn   # raises, listing registered tiers, if
                                          # tier isn't found — this is how tiers
                                          # 2/4/5 fail loudly in Milestone A rather
                                          # than silently producing wrong audio
```

`render_junction(junction, audio_a, audio_b) -> StereoPCM` resolves
`get_strategy(junction.strategy_tier)` and calls it. Adding tier 2 later
(`strategies/bass_swap.py` calling `register_strategy(2, ...)` at import time,
exactly like `llm_service`'s built-in providers) is additive — `render_junction`'s
signature never changes.

**Milestone A: only tier 3 is registered** (`strategies/cut_on_the_one.py`). Calling
`render_junction` with `strategy_tier` 2, 4, or 5 raises `UnregisteredStrategyError`
— explicit, not a silent wrong-sounding fallback.

---

## 5. Milestone A — tier 3, `cut_on_the_one.py`

```
cut_on_the_one(junction: Junction, audio_a: StereoPCM, audio_b: StereoPCM) -> StereoPCM:
  assert audio_a.sample_rate == audio_b.sample_rate == 48000        # D25
  a_slice = audio_a.samples[0 : to_sample(junction.cue_out), :]      # from the top (Milestone A)
  b_slice = audio_b.samples[to_sample(junction.cue_in) :, :]         # to natural end (D24)
  a_slice = linear_edge_fade(a_slice, sample_rate, fade_in=False)    # fades.py (§5.1)
  b_slice = linear_edge_fade(b_slice, sample_rate, fade_in=True)     # fades.py (§5.1)
  return StereoPCM(samples=concatenate([a_slice, b_slice], axis=0), sample_rate=48000)
```

**`FADE_MS = 5`** — a fixed constant, not derived from anything musical (§10's own
framing: this is DSP hygiene against a discontinuity click, not a "strategy" choice
like the tier ladder). Linear, not equal-power — over 5ms the curve shape is
inaudible; equal-power exists to keep perceived loudness constant across a *longer*
crossfade, which doesn't apply here since the two fades never overlap.

### 5.1 Shared anti-click fade (`fades.py`) — 2026-09-17 amendment

```
linear_edge_fade(segment: np.ndarray, sample_rate: int, *, fade_in: bool) -> np.ndarray
```

Promoted from a private helper inside `cut_on_the_one.py` (where `FADE_MS` still
lives — this function reads it, doesn't own a second copy) to its own module,
because `playlist_renderer`'s Milestone B body-slicer (`playlist_renderer` spec
§3, W3) needs the exact same anti-click treatment at every track-body boundary,
not just at a tier-3 junction. Behavior is byte-for-byte unchanged — same ramp,
same `FADE_MS`, same "never overlaps" property — only its location and importability
changed. `cut_on_the_one` still uses it exactly as before; **this module's own §0
invariant is untouched** — `render_junction` still takes one `Junction` in
isolation and knows nothing about track bodies, sequencing, or any other junction.
`playlist_renderer` imports `linear_edge_fade` directly; it does not call
`render_junction` for tier-3 boundaries any more (see that spec's §3 amendment for
why: an interior track needs both a fade-in *and* a fade-out on the same body,
which `render_junction`'s per-pair, whole-track-shaped contract can't express
without artificially reconstructing shifted `Junction` copies).

**Where `a_slice` starts (Milestone A): sample `0`.** `render_junction` receives only
the `Junction`, which carries no opener `cue_in`, and `render_mix` does no slicing
(`playlist_renderer` §3) — so the walking skeleton's opener plays from the top of its
file to `junction.cue_out`. This is consistent with `path_search`'s `plan_builder`,
which leaves `TrackRef.cue_in = None` on a set-opening track (D24's free cue-in).
Threading a **non-zero** opener `cue_in` — a mid-set track once Milestone B slices
track bodies — is deferred to Milestone B; it resolves §10 Q2 for Milestone A (see
Amendments 2026-08-29).

---

## 6. Milestone B — tiers 2, 4, 5 (documented, not implemented)

Not built in this pass; recorded here so the interface (§4) doesn't need to change
shape when these land.

**DSP comes from libraries, not hand-rolled code.** Each `strategies/*.py` imports
what it needs — `StrategyFn`'s signature (§4) is unchanged. `pedalboard`
(`HighpassFilter`, `LowShelfFilter` + `HighShelfFilter` for the 3-band bass swap,
`Delay` for tier 4's echo-out, `Gain`) covers tiers 2/4/5's effects; `pyrubberband`
or `librosa.effects.time_stretch` covers `rate_b` beat-lock; `playlist_renderer`'s
set-wide LUFS reuses Essentia's `LoudnessEBUR128` (already a dependency). All operate
on numpy float32 in/out (see Amendments 2026-08-29).

- **Tier 2 — bass swap** (§1.9's worked example, D19's ±3% gate): non-zero
  `length_bars`, `envelopes[]` populated per the automation curves in design-v3's
  example junction (§5.2) — kill/ramp on `low` per side, equal-power crossfader over
  the swap window. Needs `rate_b` for beat-lock (D19) — the whole reason `Envelope`
  and `rate_a`/`rate_b` are on the contract already (§2).
- **Tier 4 — echo-out**: beat-synced delay on A as it thins out, tail carries into B.
- **Tier 5 — filter fade**: high-pass A up and out over 8 bars.
- **Tempo ramp (D18) is v2, not Milestone B** — design-v3 is explicit ("v1 status:
  not needed"); `ramp_bars` stays `0` through Milestone B too.

---

## 7. Testing strategy

- **Synthetic fixtures only** — two short generated tones/click patterns
  (`conftest.py`), not real `music/` tracks (`music/` is gitignored per the
  `feature_extractor` spec's §13 precedent; this module's correctness doesn't depend
  on real content).
- `test_cut_on_the_one.py`: splice lands at the exact sample computed from
  `cue_out`/`cue_in`; output duration equals `(cue_out - A.cue_in) + (B_end -
  cue_in)`; no sample exceeds ±1.0 (no clipping introduced by the fades); fade
  actually applied (first/last `FADE_MS` samples ramp, not a hard edge).
- `test_render.py`: dispatch resolves the right strategy for tier 3; tiers 2/4/5
  raise `UnregisteredStrategyError` with the registered-tiers list in the message.
- `schema.py` has no dedicated test file — plain data classes, no behavior.

---

## 8. File layout

```
src/render/transition_renderer/
  __init__.py            # public exports: StereoPCM, Junction, Envelope,
                          # render_junction, register_strategy,
                          # UnregisteredStrategyError, linear_edge_fade
  schema.py                # StereoPCM (§2); re-exports Junction/Envelope from
                            # common.contracts.schema — not defined here (§2)
  errors.py                 # UnregisteredStrategyError
  fades.py                   # linear_edge_fade() (§5.1) — shared with
                              # playlist_renderer's Milestone B body-slicer
  render.py                   # render_junction() — dispatch (§4)
  strategies/
    __init__.py                # imports every built-in strategy module, registering
                                # each as a side effect (mirrors llm_service
                                # providers/__init__.py)
    registry.py                  # register_strategy(), get_strategy() (§4)
    cut_on_the_one.py              # tier 3 (§5) — registers itself as tier 3

tests/render/transition_renderer/
  conftest.py                 # synthetic StereoPCM fixture generator
  test_schema.py                # (only if validation logic exists beyond field types)
  test_fades.py                   # linear_edge_fade() ramp correctness (§5.1,
                                   # 2026-09-17 amendment) — direct tests now
                                   # that it's a public, importable function
  test_render.py                    # dispatch + unregistered-tier errors (§4)
  strategies/
    test_cut_on_the_one.py           # splice/fade correctness (§7)
```

---

## 9. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Equal-power crossfade at the tier-3 splice | Two independent linear fades (out on A, in on B), never overlapping (§5) | A crossfade blends the two signals — that's what tier 3 explicitly exists to avoid (§1.9: "full crossfade is excluded"). The fades here don't overlap; they're anti-click hygiene, not a blend |
| A single `render_junction` implementation with an `if tier == ...` chain | Strategy registry keyed on tier (§4) | Matches the `llm_service` provider pattern already in this repo; adding tier 2 later never touches this module's public signature |
| Silent fallback to tier 3 when a higher tier isn't implemented yet | `UnregisteredStrategyError`, explicit (§4, §7) | A silently-substituted strategy would produce audio that doesn't match what the (future) edge builder actually planned and costed — wrong in a way that's invisible until someone listens closely |
| Deriving gain matching inside this module from the tracks' own loudness | `gain_db_a`/`gain_db_b` supplied on `Junction`, defaulted to 0.0 in Milestone A | D1: the renderer decides nothing. Gain targets depend on the whole set (§4.2), which this module — callable on one junction in isolation (§0) — structurally cannot know |

---

## 10. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | `FADE_MS = 5` (§5) is an unvalidated guess at "long enough to kill a click, short enough to stay a cut" — has anyone confirmed this by ear against the walking skeleton's actual output? | Whether Milestone A's implementation needs a constant change before it's "done" |
| Q2 | ~~Where exactly does a track's own `cue_in`/`cue_out` (for the body *outside* any junction) live in `MixPlan.tracks[]`'s trimmed Milestone-A shape?~~ **Resolved** — `TrackRef.cue_in`/`cue_out` in `common/contracts/schema.py` (`path_search` spec §2). For Milestone A the opener's `a_slice` starts at sample `0` regardless (§5, Amendments 2026-08-29); consuming a non-zero opener `cue_in` is Milestone B | ~~Cross-spec consistency~~ — closed |

---

## Amendments

- **2026-09-17** — **`linear_edge_fade` promoted to a shared, public helper
  (§5.1), for W3's multi-junction assembly.** No behavior change to
  `cut_on_the_one` or `render_junction` — same ramp math, same `FADE_MS`,
  same call sites' effective output. What changes: the function moves out of
  `cut_on_the_one.py` (private `_linear_fade`) into its own `fades.py`
  (public `linear_edge_fade`), and `playlist_renderer`'s Milestone B
  body-slicer becomes a second caller.

  **Why:** `playlist_renderer` spec §3 (this same date) resolves that spec's
  §9 Q1 — an interior track in an N-track mix needs *both* a fade-in (it was
  just cut into) and a fade-out (it's about to be cut again) on the same
  body, applied at each boundary independently. `render_junction`'s contract
  (one `Junction`, two *whole* tracks, "A from 0, B to natural end") has no
  way to express that without `playlist_renderer` reconstructing
  artificially-shifted `Junction` copies and pre-trimmed buffers per call —
  fragile, and it still can't apply both fades to one body in one pass. Pulling
  the fade primitive out and letting `playlist_renderer` slice+fade each
  track's body directly is simpler and doesn't require inventing a second
  `Junction`.

  **This module's own §0 invariant is unaffected.** `render_junction` is
  still callable on a single junction in isolation, still knows nothing about
  sequencing or any other junction — it just isn't in `playlist_renderer`'s
  call path for tier-3 boundaries any more (tier 3 has no blend content to
  render, `length_bars = 0`; there was never anything for `render_junction`
  to contribute there beyond the fade math this amendment relocates).
  `render_junction` remains the right entry point for a future tier with
  real blend content (`length_bars > 0`) — `playlist_renderer` would call it
  for those junctions specifically once tiers 2/4/5 exist (§6), and use the
  direct slice+fade path only where `length_bars == 0`.

  1. **§5 / §5.1** — new `fades.py`; `cut_on_the_one.py` imports
     `linear_edge_fade` instead of defining `_linear_fade` privately.
  2. **§8** — file layout gains `fades.py` / `test_fades.py`; `__init__.py`
     exports `linear_edge_fade`.

- **2026-08-29** — **`StereoPCM` axis order, tier-3 opener slice start, and Milestone B
  DSP libraries.** Surfaced while planning W2, the first implementation of this spec. No
  code implements the spec, so this is an amendment on the same basis as the two entries
  below.
  1. **§2** — `StereoPCM.samples` shape changes from `(2, n_samples)` to **`(n_samples, 2)`**
     (channels-last), float32. This matches the `StereoPCM` that
     `ingestion/feature_extractor/loader.py` already defines and `load_canonical` returns,
     and `soundfile`'s frame-major layout — so wiring the real loader and the WAV writer
     needs zero transposes. No field renamed; `sample_rate` unchanged.
  2. **§3 / §5** — the tier-3 pseudocode's array ops follow the new axis order:
     `audio_a.samples[:, s0:s1]` → `audio_a.samples[s0:s1, :]`;
     `concatenate([a_slice, b_slice], axis=1)` → `axis=0`. The general segment-math formula
     in §3 (unused by tier 3) is unaffected.
  3. **§5 + §10 Q2** — in Milestone A the opener's `a_slice` starts at **sample 0**.
     `render_junction` receives only the `Junction` (which carries no opener `cue_in`), and
     `render_mix` does no slicing (`playlist_renderer` §3), so the walking-skeleton opener
     plays from the top of its file to `junction.cue_out`. `TrackRef.cue_in` is `None` for
     a set-opening track (`path_search` `plan_builder`), consistent with this. Consuming a
     non-zero opener `cue_in` — a mid-set track under Milestone B's body assembly — is
     deferred to Milestone B. **Q2 is resolved for Milestone A** on this basis.
  4. **§6** — the deferred tiers name their libraries rather than hand-rolled DSP:
     **`pedalboard`** for tier 2/4/5 effects (`HighpassFilter`, `LowShelfFilter` +
     `HighShelfFilter` for the 3-band bass swap, `Delay` for tier 4's echo-out, `Gain`),
     and **`pyrubberband`** or `librosa.effects.time_stretch` for `rate_b` beat-lock. Both
     are numpy float32 in/out, so `StrategyFn`'s signature (§4) is unchanged. Set-wide LUFS
     in `playlist_renderer` reuses Essentia's `LoudnessEBUR128` (already a dependency).

- **2026-08-24** — **`Junction` gained `bar_seconds`** (`edge_builder` spec **v2**
  §2/§6, which owns the contract). This module could not previously execute any tier
  with `length_bars > 0`: §3's `blend_end = blend_start + length_bars` and every
  `Envelope` breakpoint are counted in *bars*, but §4's
  `StrategyFn = Callable[[Junction, StereoPCM, StereoPCM], StereoPCM]` receives only
  the `Junction` and two PCM buffers — and nothing on the `Junction` said how long a
  bar was. The gap was invisible because **tier 3, the only implemented tier, has
  `length_bars = 0`** and degenerates to a splice (§3), so it is the one tier where
  the conversion never happens. `bar_seconds` is track A's bar length (the window is
  anchored on A's exit; tier 2 locks B to A via `rate_b`, so inside the window B's
  bars are A's), and it is emitted on every tier including tier 3, where it goes
  unused.

  An amendment, not a v2, on this spec's own established test: **no code implements
  this spec** (`overview.md` row 6: Spec Done, Code —; `src/render/` does not exist),
  so nothing can fail to comply. Same justification as the 2026-08-21 entry below.
  Surfaced while specifying `processing/path_search` — see that spec §16.
  1. §3 — the segment-boundary math now has the tempo it needs; `length_bars` and
     `ramp_bars` convert to seconds as `n * junction.bar_seconds`, then to samples at
     the canonical rate (D25), preserving §3's "sample-exact boundaries" invariant.
  2. §4 — `StrategyFn`'s signature is **unchanged**; the tempo arrives inside the
     `Junction` it already receives, which is why no interface needed to move.

- **2026-08-21** — `Junction` and `Envelope` moved out of this module's `schema.py`
  to `common/contracts/schema.py`, surfaced while drafting
  `resources/documentation/processing/edge_builder/spec.md` (§2 of that spec) — the
  first module that actually *produces* a `Junction`. Keeping the contract here would
  have made the planning layer depend on the render layer; moving it into
  `processing/` would only have inverted that. **No field changed**, and `schema.py`
  re-exports both names, so this module's public surface (§8's `__init__.py` exports)
  is identical.

  Recorded as an amendment rather than a v2, despite the README's decision table
  listing "a file path" under *New version*: that table's operative test is *"does
  code already implementing the old spec still comply?"*, and **no code implements
  this spec yet** (`overview.md` row 6: Spec Done, Code —), so nothing can fail to
  comply. Same justification `cue_derivation`'s own 2026-08-18 amendment used. Should
  this module get built before the move actually lands, re-evaluate as a version bump.
  1. §2 — `Junction`/`Envelope` field blocks replaced by an import note pointing at
     `edge_builder` spec §2 as their single owner; `StereoPCM` unchanged and still
     owned here.
  2. §8 — `schema.py`'s comment updated to record the re-export.
