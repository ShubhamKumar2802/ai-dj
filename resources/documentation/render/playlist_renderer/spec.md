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
> job is to slice each track's body, call `transition_renderer` for any junction that
> has real blend content, concatenate the results, and write output. (D1: "the
> renderer executes envelopes; it decides nothing" — applies here exactly as it does
> to `transition_renderer`.) **Untouched by the 2026-09-17 amendment** — every
> position this module slices at (`cue_in`/`cue_out`/`fade_out_bars`) still comes
> verbatim from the `MixPlan`; this module executes an already-decided assembly, it
> doesn't decide where any of those boundaries fall.

---

## 1. Scope & consumers

**Boundary:** audio-touching (§4), the top-level entry point for going from a
`MixPlan` to a playable file. Owns output format decisions (WAV now, MP3 later) —
`transition_renderer` never writes a file, it only returns `StereoPCM` in memory.

**Consumer:** whatever invokes the pipeline end-to-end — for the walking skeleton,
a hand-typed `MixPlan` fixture and a direct call; later, `path_search`'s output feeds
this module directly (§4.2: "Playlist serialisation — Output of path search —
collecting winning edges").

**Milestone A was scoped down to exactly one junction (two tracks)** — the walking
skeleton's literal scope (§10: "two hard-coded tracks"). **Milestone B (2026-09-17
amendment, §3) generalizes `render_mix()` to N≥1 tracks / N−1 junctions** — the
question of how responsibility for a middle track's exit point splits between this
module and `transition_renderer` (formerly Q1) is resolved: this module slices
every track's own body, `transition_renderer` is reserved for a junction's actual
blend content once a tier has any (§6; none does yet).

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

## 3. Orchestration — `render_mix()` (`render.py`) — Milestone B, 2026-09-17 amendment

**Every track gets exactly one body window**, bounded by whichever junctions flank
it (or, for the two tracks with no junction on one side, that side's own `TrackRef`
field — D24's relaxation):

```
entry_i = (tracks[0].cue_in or 0.0)         if i == 0        else junctions[i-1].cue_in
exit_i  = (tracks[-1].cue_out or <nat.end>)  if i == n-1       else junctions[i].cue_out
```

This is exactly what `plan_builder` already produces: every interior `TrackRef`
leaves `cue_in`/`cue_out`/`fade_out_bars` at `None` because "its flanking junctions
are authoritative" (`path_search` spec, `plan_builder.py`'s own docstring) — this
module is the first code that actually reads that comment's promise literally.

```
render_mix(mix_plan: MixPlan, load_audio: Callable[[str], StereoPCM]) -> StereoPCM
  1. n = len(mix_plan.tracks)
     if len(mix_plan.junctions) != n - 1:
         raise ValueError(...)   # structural sanity check on a well-formed MixPlan
                                 # — not a scope limit (Milestone A's == 1 junction /
                                 # == 2 tracks guard is gone, see ## Amendments).
                                 # Still a raised error, not a bare assert
  2. segments = []
     for i, track in enumerate(mix_plan.tracks):
         audio = load_audio(track.path)
         entry = (track.cue_in or 0.0) if i == 0 else mix_plan.junctions[i - 1].cue_in
         exit_ = (
             track.cue_out if (i == n - 1 and track.cue_out is not None)
             else (natural_end(audio) if i == n - 1 else mix_plan.junctions[i].cue_out)
         )
         segment = audio.samples[to_sample(entry) : to_sample(exit_), :]

         if i > 0:                        # entered via a cut — fade in
             segment = linear_edge_fade(segment, audio.sample_rate, fade_in=True)
         if i < n - 1:                    # exits via a cut — fade out
             segment = linear_edge_fade(segment, audio.sample_rate, fade_in=False)
         if i == n - 1 and track.fade_out_bars is not None:      # §9 Q3
             duration = track.fade_out_bars * mix_plan.junctions[-1].bar_seconds
             segment = equal_power_fade_to_silence(segment, audio.sample_rate, duration)

         segments.append(segment)
  3. return StereoPCM(samples=concatenate(segments, axis=0), sample_rate=SAMPLE_RATE)
```

`linear_edge_fade` is imported from `transition_renderer` (that spec's §5.1,
2026-09-17 amendment) — the same anti-click hygiene tier 3 already applies at a
splice, now applied by this module directly at every body boundary instead of via
`render_junction`. **`transition_renderer.render_junction` is not called for tier-3
junctions any more** — tier 3 (`length_bars = 0`) has no actual blend content, so
there was never anything for it to contribute beyond the fade math this amendment
relocates. It remains the right call for a future tier with real blend content: once
tiers 2/4/5 exist (§6), step 2 would call `render_junction(junctions[i], ...)` for
any junction where `length_bars > 0`, splicing its output between the shortened
`A_body` and `B_body` either side — out of scope here since no such tier exists yet.

`equal_power_fade_to_silence(segment, sample_rate, duration_seconds)` is new,
defined in this module (`render.py`) — §9 Q3's fallback, now with somewhere to live.
Equal-power (not linear, unlike the anti-click fade) per Q3's original wording;
`duration_seconds` anchored on `junctions[-1].bar_seconds` — the last junction's own
`bar_seconds` (track N-2's bar length), a reasonable stand-in for the closer's own
bar length rather than an exact one, same spirit as `Junction.bar_seconds` itself
being "track A's bar length" everywhere else in this pipeline (`edge_builder` spec
v2 §6).

`load_audio` is an **injected dependency**, not a hardcoded decoder call — this is
what keeps `render_mix()` testable against synthetic `StereoPCM` fixtures (§6)
without touching a real file, the same reasoning `feature_extractor`'s spec applies
to keeping DSP calls behind named functions rather than inlined. In real use it's
backed by the same canonical loader described in `feature_extractor`'s spec §3
(48kHz float32 stereo, D25) — this module doesn't reimplement audio loading, it
reuses that one.

**This subsumes Milestone A exactly** — for `n = 2`, track 0 gets a fade-out only
(matching the old `a_slice`) and track 1 gets a fade-in only plus whatever
`fade_out_bars` says (matching the old `b_slice`, with Q3 now actually implemented
instead of silently absent). Numerically identical output to the old two-line
delegation to `render_junction`, so there is only ever one code path here now, not
one for N=2 and a separate one for N>2.

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
  `transition_renderer`. The per-track loudness comes from `TrackRef.lufs_integrated`
  (already carried on the contract); the set-level target is metered with Essentia's
  `LoudnessEBUR128`, already a dependency via `feature_extractor` — not a hand-rolled
  BS.1770 meter (see Amendments 2026-08-29). MP3 encoding, when it lands, is a final
  `soundfile`/`ffmpeg` step (D17: never run DSP on lossy audio).

---

## 6. Testing strategy

- **Synthetic fixtures**, same pattern as `transition_renderer`'s tests
  (`conftest.py` generates short `StereoPCM` tones) — no real `music/` files in the
  automated suite.
- `test_render.py`: `render_mix()` against a fake `load_audio` returning synthetic
  fixtures. Milestone B (2026-09-17): a 2-track fixture reproduces Milestone A's
  exact output byte-for-byte (subsumption, §3); a 3+ track fixture asserts every
  interior track gets *both* a fade-in and a fade-out (the case Milestone A never
  exercised); a closer with `fade_out_bars` set asserts the tail actually ramps to
  ~silence over the expected duration (§9 Q3, finally testable); the structural
  `len(junctions) != len(tracks) - 1` guard raises (a malformed-plan check now, not
  a scope limit).
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
  render.py                   # render_mix() (§3), equal_power_fade_to_silence() (§3, §9 Q3)
  writer.py                     # write_wav() (§4)

tests/render/playlist_renderer/
  conftest.py                # synthetic StereoPCM fixtures, fake load_audio
  test_schema.py               # (only if validation logic exists beyond field types)
  test_render.py                 # render_mix() orchestration incl. multi-junction
                                  # body-slicing + fade_out_bars, structural guard (§6)
  test_writer.py                   # WAV round-trip (§6)
```

---

## 8. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Silently truncate/ignore extra tracks on a >2-track `MixPlan` (Milestone A) | Explicit `assert`/error on `len(junctions) != 1` | Milestone A's scope limit should fail loudly the moment it's exceeded, not quietly render a wrong 2-track excerpt of a bigger plan. Superseded 2026-09-17: Milestone B removes the scope limit itself (N≥1 is the real shape now), but the *reasoning* — fail loudly on a structurally malformed `MixPlan` rather than rendering something wrong — is why §3 step 1's `len(junctions) != len(tracks) - 1` check stays a raised error, not a bare `assert` |
| Reuse `transition_renderer.render_junction` per-pair for Milestone B, gluing consecutive calls' outputs together | Each track's body sliced once by this module; `render_junction` reserved for actual blend content (§3, 2026-09-17) | Per-pair reuse double-renders every interior track's body (once as a junction's "B", again as the next junction's "A") with *different* fades applied to each copy (fade-in only from one call, fade-out only from the other) — merging them back into one correctly-double-faded body is more complex than slicing once and fading both edges directly |
| Have this module decode audio directly (e.g. call Essentia/librosa inline) | `load_audio` injected as a parameter (§3) | Keeps `render_mix()` testable against synthetic fixtures with zero real decode cost, same reasoning as `feature_extractor`'s named-function boundaries |
| Apply a default/guessed gain normalization in Milestone A since no LUFS data exists yet | `gain_db_a`/`gain_db_b` stay `0.0`, unity, until real LUFS data exists (§4) | A guessed gain is worse than no gain correction — it would look like a deliberate mastering decision instead of the honestly-absent feature it is |

---

## 9. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | ~~Shared with `transition_renderer`'s open questions. Does the D17 three-way `A_body`/`junction`/`B_body` split get implemented here, or does `transition_renderer` grow a "max duration for B" parameter instead?~~ **Resolved 2026-09-17 — spec only, not yet implemented.** This module slices every track's own body (§3); `transition_renderer` is reserved for a junction's actual blend content, which no implemented tier has yet | `render_mix()`'s design, now written (§3). **`render.py`/`writer.py` still implement the old Milestone-A-only version** — code needs to catch up before this is real |
| Q2 | Where does `load_audio` actually live — a shared utility both `feature_extractor` and this module import, or does this module get its own thin wrapper around the same canonical loader? | Avoiding two independent implementations of "decode to 48kHz float32 stereo" (D25) drifting apart |
| Q3 | ~~`TrackRef.fade_out_bars` has no Milestone A implementation...~~ **Resolved 2026-09-17 — spec only, not yet implemented.** §3's `render_mix` now applies `equal_power_fade_to_silence` on the closer's tail whenever `fade_out_bars` is set (true on every real mix in v1, since `cue_derivation` never emits `outro_start` — `relax_closer`'s other two branches both set it) | The last few seconds of every rendered mix — no longer a hard stop once implemented |

---

## Amendments

- **2026-09-17** — **Milestone B: `render_mix()` generalizes to N≥1 tracks,
  resolving Q1 and Q3.** Spec-only — `render.py`/`writer.py` are not yet
  updated to match (the next implementation step, not drift).

  **§1 / §3** — the Milestone-A `== 1 junction / == 2 tracks` scope limit is
  gone. `render_mix` now computes every track's own body window
  (`entry_i`/`exit_i`, from its flanking junctions or, at the two open ends,
  D24's relaxed `TrackRef` fields), slices and fades each one, and
  concatenates. Resolves this spec's Q1 (and `transition_renderer`'s matching
  question) in favor of *"this module slices bodies"*: `transition_renderer`'s
  own §0 invariant — `render_junction` callable on one junction in isolation
  — is incompatible with the alternative (`transition_renderer` growing a
  "max duration for B" parameter would require knowing where the *next*
  junction falls, context a single-junction call structurally cannot have).

  **Not a same-day accident that both render specs changed together** — see
  `transition_renderer`'s own 2026-09-17 amendment, which promotes the shared
  `linear_edge_fade` helper this module's new body-slicer imports.

  **§3 / §9 Q3** — `TrackRef.fade_out_bars` finally has somewhere to live: the
  closer's body gets `equal_power_fade_to_silence` applied to its tail
  whenever `fade_out_bars` is set, which per `relax_closer`
  (`path_search/boundaries.py`) is every real v1 mix. Every rendered set's
  ending changes from a hard stop to an actual fade once this lands in code.

  **Subsumes Milestone A exactly** — for `n = 2` the new general path produces
  byte-identical output to the old direct `render_junction` delegation (§3
  spells out why); there is one code path now, not two.

  1. §1 — Milestone-A-only scope language replaced; Milestone B is now the
     documented general case.
  2. §3 — full rewrite: `entry_i`/`exit_i` windowing, per-track fade rules,
     `equal_power_fade_to_silence`, the structural (not scope-limiting)
     `len(junctions) != len(tracks) - 1` guard.
  3. §6 — test plan covers multi-junction body-slicing, both-edges fading on
     interior tracks, and `fade_out_bars`'s tail fade (all newly testable).
  4. §8 — rejected-alternatives row added: per-pair reuse of
     `render_junction` for N>2 was considered and rejected (double-renders
     every interior body with mismatched fades on each copy).
  5. §9 — Q1 and Q3 marked resolved, pointing here.

- **2026-08-29** — **`render_mix` scope guard realized as a raised error; Milestone B
  library note.** Surfaced while planning W2 (the first implementation of this spec). No
  code implements the spec.
  1. **§3** — the `len(mix_plan.junctions) == 1 and len(mix_plan.tracks) == 2` scope limit
     is implemented as an explicit `raise ValueError`, not a bare `assert`, so it survives
     `python -O`. §8's rejected-alternatives row already frames this as *"explicit
     `assert`/error"*; this pins it to the error form. `transition_renderer`'s
     `sample_rate == 48000` check stays a plain `assert` (a defensive invariant, not a
     caller-facing scope guard).
  2. **§5** — Milestone B's LUFS-based gain step meters its set-level target with Essentia's
     `LoudnessEBUR128` (already a dependency via `feature_extractor`), not a hand-rolled
     BS.1770 meter; MP3 encoding is a final `soundfile`/`ffmpeg` step per D17. Mirrors
     `transition_renderer`'s 2026-08-29 amendment so the two render specs stay consistent on
     "libraries do the DSP".
  3. `StereoPCM` — this spec never restated the array shape, so `transition_renderer`'s flip
     to `(n_samples, 2)` needs no change here.

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
