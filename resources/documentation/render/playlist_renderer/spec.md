# Playlist Renderer — Spec

**Layer:** `render/` — second module in this layer, alongside `transition_renderer`.
**Depends on:** `resources/documentation/render/transition_renderer/spec.md`'s
`StereoPCM`/`Junction` contracts.
**Implementation staged in two milestones** (§5), same split as
`transition_renderer`: Milestone A (WAV only, walking skeleton) now; Milestone B
(MP3, CUE sheet, segment caching) once `edge_builder`/`path_search` exist.

---

## 0. Invariant

> **This module decides nothing about the audio, only about assembly and encoding.**
> Every gain value, cue point, and strategy came from the `MixPlan`; this module's
> job is to call `transition_renderer` for each junction, concatenate the results,
> and write output. (D1: "the renderer executes envelopes; it decides nothing" —
> applies here exactly as it does to `transition_renderer`.)

---

## 1. Scope & consumers

**Boundary:** audio-touching (§4), the top-level entry point for going from a
`MixPlan` to a playable file. Owns output format decisions (WAV now, MP3 later) —
`transition_renderer` never writes a file, it only returns `StereoPCM` in memory.

**Consumer:** whatever invokes the pipeline end-to-end — for the walking skeleton,
a hand-typed `MixPlan` fixture and a direct call; later, `path_search`'s output feeds
this module directly (§4.2: "Playlist serialisation — Output of path search —
collecting winning edges").

**Explicitly scoped down for Milestone A:** this module's `render_mix()` only
supports **exactly one junction (two tracks)** — the walking skeleton's literal
scope (§10: "two hard-coded tracks"). Generalizing to N>2 tracks / multiple
junctions is deferred to Milestone B and is a **shared open question with
`transition_renderer`** (§7's Q1) — solving it well likely means revisiting how the
two modules split responsibility for a middle track's exit point, not just adding a
loop here.

---

## 2. Data contracts (`schema.py`)

**`MixPlan`, `TrackRef` and `MixPlanConfig` are imported from
`common/contracts/schema.py`**, not defined here — `schema.py` re-exports them so this
module's public surface is unchanged. Their field lists live in
`resources/documentation/processing/path_search/spec.md` §2, which is now their single
owner: `path_search` is the module that actually *produces* a `MixPlan`.

They were originally defined here, back when nothing produced one and a hand-typed
fixture was the only source. That ownership predates `processing/path_search`; leaving
the contract in `render/` would make the planning layer depend on the render layer,
and moving it into `processing/` would only invert the same problem — the identical
reasoning that moved `Junction`/`Envelope` to `common/contracts/` (see
`## Amendments`, and `processing/edge_builder` spec §2). `StereoPCM` stays in
`render/transition_renderer/schema.py` — audio-only, never crosses into planning.

Two fields are new since the Milestone-A shape this spec originally carried, both set
by `path_search` and both consumed here rather than by `transition_renderer`:

- **`TrackRef.fade_out_bars : int | None`** — D24's closer fallback. When the last
  track has no `outro_start` cue (which is always, in v1), `path_search` sets a
  time-boxed `cue_out` **and** `fade_out_bars = 4`, meaning *"apply a 4-bar
  equal-power fade to silence"* rather than stopping dead. `None` everywhere else.
  Honoured in Milestone B (§9 Q3).
- **`TrackRef.lufs_integrated : float`** — carried through from `Track` so that this
  module can compute set-wide gain. It closes a real gap: `edge_builder` §1 leaves
  `gain_db_a/b` at `0.0` calling gain *"`playlist_renderer`'s concern"*, and
  `transition_renderer` §3 declines it because *"that needs LUFS data this module
  never receives"* — but `render_mix(mix_plan, load_audio)` receives no `Track[]`
  either, so the job had an owner with no access to its input. Milestone B's
  mastering step reads this field.

Milestone A's fixture always has exactly `tracks = [A, B]`, `junctions = [one
Junction]`, with `A.cue_out` and `B.cue_in` left unset (both are supplied by the
`Junction` instead — `junction.cue_out`/`junction.cue_in` are the authoritative
values whenever a junction exists on that side; `TrackRef.cue_in`/`cue_out` are only
consulted for the unconstrained D24 ends).

---

## 3. Orchestration — `render_mix()` (`render.py`)

```
render_mix(mix_plan: MixPlan, load_audio: Callable[[str], StereoPCM]) -> StereoPCM
  1. assert len(mix_plan.junctions) == 1 and len(mix_plan.tracks) == 2   # Milestone
                                                                          # A's explicit
                                                                          # scope limit
                                                                          # (§1) — fails
                                                                          # loudly, not
                                                                          # silently
                                                                          # wrong, on a
                                                                          # 3+ track plan
  2. audio_a = load_audio(mix_plan.tracks[0].path)
     audio_b = load_audio(mix_plan.tracks[1].path)
  3. return transition_renderer.render_junction(mix_plan.junctions[0], audio_a, audio_b)
```

`load_audio` is an **injected dependency**, not a hardcoded decoder call — this is
what keeps `render_mix()` testable against synthetic `StereoPCM` fixtures (§6)
without touching a real file, the same reasoning `feature_extractor`'s spec applies
to keeping DSP calls behind named functions rather than inlined. In real use it's
backed by the same canonical loader described in `feature_extractor`'s spec §3
(48kHz float32 stereo, D25) — this module doesn't reimplement audio loading, it
reuses that one.

Because `transition_renderer.render_junction`'s Milestone-A contract already
produces "A's full body through the splice, plus B from its cue-in to its own
natural end" (transition_renderer spec §5) — for exactly two tracks and one
junction, its return value **is** the complete mix. `render_mix()` does no
additional slicing or concatenation in Milestone A; that only becomes real once
Milestone B's multi-junction case exists.

---

## 4. Output — WAV writing (`writer.py`)

**Milestone A: WAV only.**

```
write_wav(audio: StereoPCM, output_path: str) -> None
```

48kHz float32 stereo straight through — the canonical format (D25) is never
converted or downmixed on the way out. No mastering/loudness step in Milestone A
(no LUFS data exists yet — `feature_extractor` isn't built); `gain_db_a`/
`gain_db_b` on the `Junction` are `0.0` and stay that way until Milestone B.

---

## 5. Milestone B (documented, not implemented)

- **MP3 encoding, final step only** (D17: "never run DSP on lossy audio") — master
  to WAV first, exactly as Milestone A already does, then encode.
- **CUE sheet + plain timestamp list** (D17) — derived from `MixPlan.junctions[]`'
  cue positions plus each segment's rendered duration; needs the real multi-junction
  case to be meaningful.
- **Junction segment caching** on `hash(A, cue_out, B, cue_in, strategy, params)`
  (D17) — lives here, not in `transition_renderer`, since caching is about reusing
  *this module's* assembly work across replans, not about the pure per-junction
  render function itself.
- **LUFS-based gain application** (§4.2: "LUFS application — Renderer — target
  depends on the set, not the track") — this module computes the set-level target
  and sets real `gain_db_a`/`gain_db_b` values before calling
  `transition_renderer`, once `feature_extractor` supplies `lufs_integrated` per
  track.

---

## 6. Testing strategy

- **Synthetic fixtures**, same pattern as `transition_renderer`'s tests
  (`conftest.py` generates short `StereoPCM` tones) — no real `music/` files in the
  automated suite.
- `test_render.py`: `render_mix()` against a fake `load_audio` returning synthetic
  fixtures; asserts it delegates correctly to `transition_renderer.render_junction`
  and returns its result unchanged (Milestone A); asserts the explicit
  `len(junctions) == 1` guard raises on a larger fixture (proves the scope limit is
  enforced, not just documented).
- `test_writer.py`: `write_wav()` round-trips — write then read back with
  `soundfile`, assert sample-identical, correct sample rate and channel count.

---

## 7. File layout

```
src/render/playlist_renderer/
  __init__.py             # public exports: MixPlan, TrackRef, render_mix, write_wav
  schema.py                 # re-exports MixPlan, TrackRef, MixPlanConfig and
                             # Junction from common/contracts/schema.py — none of
                             # them defined here (§2, ## Amendments). Keeps this
                             # module's public surface unchanged
  render.py                   # render_mix() (§3)
  writer.py                     # write_wav() (§4)

tests/render/playlist_renderer/
  conftest.py                # synthetic StereoPCM fixtures, fake load_audio
  test_schema.py               # (only if validation logic exists beyond field types)
  test_render.py                 # render_mix() orchestration + scope-limit guard (§6)
  test_writer.py                   # WAV round-trip (§6)
```

---

## 8. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Silently truncate/ignore extra tracks on a >2-track `MixPlan` | Explicit `assert`/error on `len(junctions) != 1` (§3) | Milestone A's scope limit should fail loudly the moment it's exceeded, not quietly render a wrong 2-track excerpt of a bigger plan |
| Have this module decode audio directly (e.g. call Essentia/librosa inline) | `load_audio` injected as a parameter (§3) | Keeps `render_mix()` testable against synthetic fixtures with zero real decode cost, same reasoning as `feature_extractor`'s named-function boundaries |
| Apply a default/guessed gain normalization in Milestone A since no LUFS data exists yet | `gain_db_a`/`gain_db_b` stay `0.0`, unity, until real LUFS data exists (§4) | A guessed gain is worse than no gain correction — it would look like a deliberate mastering decision instead of the honestly-absent feature it is |

---

## 9. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | **Shared with `transition_renderer`'s open questions.** Milestone A's `render_junction` contract (produces A's full body + B to its natural end) only works because there's exactly one junction. Once Milestone B needs N>2 tracks, does the D17 three-way `A_body`/`junction`/`B_body` split get implemented here (this module slices each track's body, `transition_renderer` only ever renders the blend window), or does `transition_renderer` grow a "max duration for B" parameter instead? | `render_mix()`'s design once multi-junction `MixPlan`s exist (Milestone B, after `edge_builder`/`path_search`) |
| Q2 | Where does `load_audio` actually live — a shared utility both `feature_extractor` and this module import, or does this module get its own thin wrapper around the same canonical loader? | Avoiding two independent implementations of "decode to 48kHz float32 stereo" (D25) drifting apart |
| Q3 | `TrackRef.fade_out_bars` (§2, set by `path_search` per D24) has **no Milestone A implementation** — `render_mix` currently returns `transition_renderer`'s output unchanged, which plays B to its natural end with no fade. In v1 `cue_derivation` never emits an `outro_start` cue, so the fallback fires on **every** mix, meaning every closer currently ends on a hard stop | The last few seconds of every rendered mix. Trivial once Milestone B's multi-junction assembly exists — an equal-power ramp over `fade_out_bars * junction.bar_seconds` — but it has nowhere to live until this module slices track bodies itself |

---

## Amendments

- **2026-08-24** — **`MixPlan`/`TrackRef` ownership moved to
  `common/contracts/schema.py`**, and both gained fields. Surfaced while drafting
  `resources/documentation/processing/path_search/spec.md` — the first module that
  actually *produces* a `MixPlan`, and the module the 2026-08-21 entry below said this
  question was deferred until (`processing/edge_builder` spec v1 §12 Q6, now answered
  in that spec's v2).

  An amendment rather than a v2, on the same test the entry below applies: the
  README's decision table asks *"does code already implementing the old spec still
  comply?"*, and **no code implements this spec** (`overview.md` row 7: Spec Done,
  Code —; `src/render/` does not exist), so nothing can fail to comply. Should this
  module get built before the move lands, re-evaluate as a version bump.
  1. §2 — `MixPlan`/`TrackRef` field blocks replaced by an import note pointing at
     `processing/path_search` spec §2 as their single owner.
  2. §2 — `TrackRef` gains **`fade_out_bars`** (D24's 4-bar fade to silence on a
     closer with no `outro_start` cue) and **`lufs_integrated`** (so this module's
     Milestone B mastering step can reach the LUFS data it was assigned but had no
     path to — `render_mix` never receives `Track[]`).
  3. §2 — `MixPlan` gains **`config : MixPlanConfig`**, restoring design-v3 §5.2's
     config block that Milestone A's trimmed shape had dropped.
  4. §9 — new Q3 recording that `fade_out_bars` has no Milestone A implementation.

- **2026-08-21** — `Junction`'s owning module changed from
  `render/transition_renderer/schema.py` to `common/contracts/schema.py`, surfaced
  while drafting `resources/documentation/processing/edge_builder/spec.md` (§2 of
  that spec) — the first module that actually *produces* a `Junction`. **No field
  changed**, and this module still imports rather than redefines it; only the import
  source moved. See `transition_renderer`'s own `## Amendments` for the full
  rationale and for why this is an amendment rather than a version bump (no code
  implements either render spec yet — `overview.md` rows 6–7: Spec Done, Code —).
  1. §2 — `MixPlan.junctions[]`'s comment updated to name the new source.

  `MixPlan`/`TrackRef` themselves stay owned here for now. They are produced by
  `path_search`, which isn't specced yet; moving them alongside `Junction` would
  restructure this spec for a module nobody has written (tracked as `edge_builder`
  spec §12 Q6).
