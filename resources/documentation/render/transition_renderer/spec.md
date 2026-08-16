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
  samples      : np.ndarray   # shape (2, n_samples), float32
  sample_rate  : int          # must be 48000 (D25) — carried explicitly on the
                               # value itself, not assumed by the caller; every
                               # function in this module asserts it rather than
                               # trusting the field silently

Junction:                     # trimmed MixPlan.junctions[] entry (§5.2) — same
                               # field names as the full contract, Milestone-B
                               # fields simply unpopulated/defaulted for now, so a
                               # Milestone-A fixture stays valid once B lands
  from_track      : str       # track id
  to_track        : str       # track id
  cue_out         : float     # seconds, into track A
  cue_in          : float     # seconds, into track B
  strategy_tier   : int       # 2 | 3 | 4 | 5 — only 3 implemented (§4)
  ramp_bars       : int       # 0 in v1 (D18) — always 0 for the tiers this spec
                               # implements; present on the contract, not acted on
  length_bars     : int       # 0 for tier 3 (§3) — real for tier 2 (Milestone B)
  rate_a          : float     # default 1.0 — Milestone B (D19)
  rate_b          : float     # default 1.0 — Milestone B (D19)
  gain_db_a       : float     # default 0.0 — Milestone A has no LUFS data to set
                               # this from; real value is playlist_renderer's
                               # concern once feature_extractor exists
  gain_db_b       : float     # default 0.0
  envelopes       : list[Envelope]   # [] in Milestone A — tier 2's automation
                                       # curves (§1.9's worked example), Milestone B

Envelope:                     # Milestone B shape, pinned now so tier 2 doesn't
                               # need a schema change later
  target       : "low" | "mid" | "high" | "crossfader"
  side         : "a" | "b"
  breakpoints  : list[tuple[float, float]]   # (bar_offset, value) pairs
```

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

**Tier 3 degenerates this to zero length.** With `ramp_bars = 0` and
`length_bars = 0`: `junction_start = blend_start = blend_end = cue_out`. There is no
blend region — `render_junction` for tier 3 is exactly:

```
output = fade_out(A.samples[A.cue_in : cue_out], FADE_MS) ++ fade_in(B.samples[cue_in : B_end], FADE_MS)
```

a literal splice, not a blend — the two fades below don't overlap (§4's anti-click
treatment is not a tier-2-style crossfade wearing a different name).

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
  a_slice = audio_a.samples[:, to_sample(audio_a's A.cue_in) : to_sample(junction.cue_out)]
  b_slice = audio_b.samples[:, to_sample(junction.cue_in) : ]        # to natural end (D24)
  a_slice = linear_fade_out(a_slice, FADE_MS)
  b_slice = linear_fade_in(b_slice, FADE_MS)
  return StereoPCM(samples=concatenate([a_slice, b_slice], axis=1), sample_rate=48000)
```

**`FADE_MS = 5`** — a fixed constant, not derived from anything musical (§10's own
framing: this is DSP hygiene against a discontinuity click, not a "strategy" choice
like the tier ladder). Linear, not equal-power — over 5ms the curve shape is
inaudible; equal-power exists to keep perceived loudness constant across a *longer*
crossfade, which doesn't apply here since the two fades never overlap.

**Where `A.cue_in` comes from for tier 3's `a_slice` start:** for a track with no
preceding junction (the walking skeleton's track A, or any set-opening track under
D24), it's the track's own `cue_in` from its `MixPlan.tracks[]` entry — not something
this module derives; `playlist_renderer` is responsible for supplying the right start
point for whichever track sits at each position (§ of that spec).

---

## 6. Milestone B — tiers 2, 4, 5 (documented, not implemented)

Not built in this pass; recorded here so the interface (§4) doesn't need to change
shape when these land.

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
                          # UnregisteredStrategyError
  schema.py                # StereoPCM, Junction, Envelope (§2)
  errors.py                 # UnregisteredStrategyError
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
  test_render.py                  # dispatch + unregistered-tier errors (§4)
  strategies/
    test_cut_on_the_one.py         # splice/fade correctness (§7)
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
| Q2 | Where exactly does a track's own `cue_in`/`cue_out` (for the body *outside* any junction) live in `MixPlan.tracks[]`'s trimmed Milestone-A shape? Referenced here (§5) but owned by `playlist_renderer`'s spec | Cross-spec consistency — resolve when drafting `playlist_renderer/spec.md` |
