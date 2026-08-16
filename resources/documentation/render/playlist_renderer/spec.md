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

```
MixPlan:                      # trimmed §5.2 shape for Milestone A
  tracks    : list[TrackRef]
  junctions : list[Junction]  # imported from transition_renderer's schema.py —
                               # not redefined here; one contract, one owner

TrackRef:
  id       : str
  path     : str
  cue_in   : float | None     # this track's own opening point — used only when it
                               # has no preceding junction (D24's free first-track
                               # cue-in). None means "from 0.0".
  cue_out  : float | None     # this track's own closing point — used only when it
                               # has no following junction (D24: last track plays to
                               # its natural end, no time-boxing). None means "to the
                               # end of the file".
```

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
  schema.py                 # MixPlan, TrackRef (§2) — imports Junction from
                             # transition_renderer.schema
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
