# Render Stage

Part of [resources/documentation/pipeline/](00_pipeline_map.md). Covers the deterministic
execution half of the pipeline (design-v3 **D1**, **D16**) — audio and a finished
`MixPlan` in, one WAV out. This stage decides nothing; every timestamp, tier, and envelope
was already fixed during Planning.

Precise field lists, formulas, and defaults live in each module's own `spec.md`, linked
below. This file gives the mental model, not the contract.

---

## 0. Stage boundary

The renderer is a dumb executor by design (**D1**): it needs direct PCM access (the
"audio bypass" line in the architecture), but it makes zero musical decisions. Everything
it does — where to cut, which strategy tier, what gain, what envelope shape — comes
straight from the `MixPlan` handed to it. This is also why the pipeline's deliverable is a
**pre-rendered file**, not a live-skipping engine (**D16**) — live playback would need
real-time rendering, a different discipline, kept as a clean future seam over the same
`MixPlan` rather than a v1 concern.

---

## 1. Stage map

```
MixPlan + audio files
    │
    ▼  render/transition_renderer   (one junction -> one rendered segment, per strategy tier)
    ▼  render/playlist_renderer     (walks the whole MixPlan: slices each track's body
                                      between its flanking junctions, applies fades,
                                      concatenates)
one continuous WAV
```

---

## 2. Milestone A vs. B

Two build milestones, both done in the working tree:

- **Milestone A** — the walking skeleton: one junction, two tracks, one rendered WAV.
- **Milestone B** — multi-junction assembly: a full N-track `MixPlan` renders to one
  continuous WAV. `playlist_renderer` no longer calls `transition_renderer.render_junction`
  for tier-3 (cut) boundaries at all — there's no blend content to render at a cut, so a
  shared `linear_edge_fade` helper (promoted out of `transition_renderer`'s own tier-3
  strategy) is used directly at every track-body boundary instead. `render_junction`
  remains the entry point reserved for a future tier with real blend content
  (`length_bars > 0`).

Rendering already generalizes to N tracks with no change in approach once order and
per-junction decisions exist for all of them — Milestone B is exactly this: `MixPlan`
carries `tracks[]` (the order) and `junctions[]` (one fewer, each independently decided by
`edge_builder`), and `playlist_renderer` is one pass over the whole sequence, not N
independent 2-track renders glued together afterward.

---

## 3. `render/transition_renderer`

Renders one junction in isolation: `render_junction(junction, audio_a, audio_b) ->
StereoPCM`, dispatching to a strategy function registered per tier (a registry pattern
mirroring `llm_service`'s provider registry). **Only tier 3 (cut-on-the-1) is implemented**
today — a literal splice with a 5ms anti-click fade on each side, not a crossfade. Tiers
2, 4, and 5 are documented in the spec but raise `UnregisteredStrategyError` — explicitly
not implemented, not silently degraded.

Full detail: [spec](../render/transition_renderer/spec.md).

---

## 4. `render/playlist_renderer`

Walks a full `MixPlan`: for each track, computes its body window (`entry`/`exit`) from
its two flanking junctions' cue points — the first and last tracks get D24's "relaxed
ends" treatment (an unconstrained opener side, and a musical fade-out on the closer
instead of a hard time-boxed cut when no real `outro_start` exists) — applies the
appropriate anti-click or equal-power fade at each boundary, and concatenates every
track's slice into one continuous `StereoPCM`, written to disk via `write_wav`.

Full detail: [spec](../render/playlist_renderer/spec.md).

---

## 5. Proof point

A real 15-track gold-set corpus already renders end-to-end today: 12 of 15 tracks survive
quarantine (a `feature_extractor`/`cue_derivation` upstream issue, not a render defect),
averaging ~80s/track, producing one continuous ~16-minute WAV — in range of design-v3's
reference target (~15 tracks, ~17 minutes).

---

## 6. Known gaps

Tiers 2, 4, and 5 are specced but not implemented (`overview.md`'s **W5**, blocked on tier
2 specifically until `feature_extractor`'s T1 defect is resolved — until then, tier 2 is
never selected by Planning regardless of whether it's renderable). No time-stretch, no
set-wide LUFS gain pass, and no MP3/CUE-sheet export exist yet — all Milestone B/C
concerns, not required for the current WAV output.
