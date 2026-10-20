# Design

## Context

See proposal.md (Why) for the motivation. The current state that shapes the approach:

- `feature_extractor` decodes to 48 kHz stereo (`load_canonical`) and caches `RawFeatures` by `(content_hash, extractor_version)` under `.cache/feature_extractor/`. `RawFeatures.per_bar_features[i]` carries each bar's own `start_time`/`end_time`, aligned with `downbeat_times`. It also provides `bpm`, `duration` and `lufs_integrated`.
- `render/transition_renderer` implements only tier 3, `cut_on_the_one(junction, audio_a, audio_b)`: A from sample 0 to `cue_out`, then B from `cue_in` to its end, with 5 ms `linear_edge_fade`s at the seam. `Junction` has `gain_db_a/b` and `rate_a/b` fields, but the cut strategy ignores them, and nothing in `render/` time-stretches or overlaps.
- `waveform_llm_transition` set the experiment conventions to copy: pydantic config with `extra="forbid"`, a `run_experiment.py` that sets `sys.path[0]` to `src/` and changes directory to the repo root, `outputs/<pair_id>/`, `summary.md`, and `ground_truth.yaml`. Its adhoc run used this experiment's live input pair:
  - A is `music/gold-set/＂Subha Hone Na De Full Song＂… [Y7G-tYRzwYY].mp3` (132.0 BPM, 149 bars, −8.1 LUFS).
  - B is `music/Lat Lag Gayee Lyrical - Race 2 … [KxCjVIFxZNo].mp3` (130.7 BPM, 135 bars, −12.5 LUFS).
  - For that pair the user's own exit pick was bar 73, and the waveform LLM's notes put breakdowns at A's bars 41 and 73.

## Goals / Non-Goals

**Goals:**
- Pair in, listenable full-length mixed tracks out, with A left at its first real vocal gap after its opening and B entered at its intro.
- An exit choice that is easy to predict from A's vocal lane image.
- Hard cut, short overlap and bass swap rendered from the same exit/entry, so the only difference between them is the transition style.

**Non-Goals:**
- Separating B or checking B's intro for vocals. B's intro is assumed to be a valid entry.
- Choosing among several exits or entries, or any scoring.
- Time-stretching, resampling or beat-matching B to A's tempo. The input pair is assumed to be at about the same BPM, and a later module placed before this one will make sure it is. The drift is reported, not corrected, and no pair is rejected for its BPM difference.
- Changing `render/`, `edge_builder`, `cue_derivation` or `vocal_band.py`.

## Decisions

### Module layout

`src/experiments/vocal_free_windows/`:

| File | Role |
|---|---|
| `config.yaml` / `config.py` | pair, separator, windows, exit, render, outputs settings. Every field required, unknown keys are errors |
| `separation.py` | the only module that imports `demucs`/`torch` (imported inside the function). 48 kHz stereo in, 48 kHz stereo vocal stem out |
| `stem_cache.py` | `(content_hash, separator_version)` → stem WAV under `.cache/vocal_free_windows/` |
| `levels.py` | per-bar RMS of the stem (pure numpy) |
| `windows.py` | threshold and run-length logic giving `Window(first_bar, last_bar, start_s, end_s)`, plus the exit pick (pure) |
| `mix.py` | the hard cut via `cut_on_the_one`, the overlap via a local equal-power crossfade, the B gain, and the `transition_span` helper (start/end samples of an N-bar span from A's downbeats) |
| `bass_swap.py` | the 16-bar bass swap: crossover split and the three-stage gain curves (pure numpy/scipy) |
| `plot.py` | the vocal lane PNG of A |
| `report.py` | `summary.md` |
| `run_experiment.py` | CLI: `[--config PATH] [--a PATH --b PATH]` |

`levels` and `windows` never touch audio files, so they're tested with small hand-built series. `separation` is the only heavy module, and it only ever runs on A.

### Separator: Demucs `htdemucs`, through `demucs.pretrained` + `demucs.apply`

Load the model with `get_model(model_name)`, then call `apply_model(model, wav, shifts, split=True, overlap)` and keep the `vocals` source. Audio is resampled from 48 kHz to the model's 44.1 kHz and back, so the stem lines up sample-for-sample with the feature extractor's bar times. The device is `mps` if available, otherwise `cpu`, and can be set in config.

- *Alternatives:* `htdemucs_ft` gives better vocals but is about 4× slower. It is a config value, so it can be tried without code changes. Spleeter is TensorFlow-based, old, and separates vocals worse. `demucs.api` is not used because it is not in the 4.0.1 PyPI release.
- `separator_version` = `f"{model}|shifts={shifts}|overlap={overlap}|v1"`. The trailing `v1` is bumped by hand when the pre- or post-processing code changes. The cache file is `sha256(content_hash|separator_version).wav`, 16-bit stereo, written atomically (temp file + rename).

### Per-bar level and windows

- `level[i]` = RMS of the mono-summed stem over bar i's `[start_time, end_time)`.
- `level_db = 20·log10(level + 1e-10)`, and the reference is A's 95th-percentile `level_db`.
- A bar is vocal-free when `level_db < max(reference − threshold_db, floor_dbfs)`. On a normal track the relative term sets the cutoff. On a silent stem the reference collapses, so `floor_dbfs` takes over and every bar is vocal-free.
- A window is a run of at least `min_bars` vocal-free bars.

Defaults: `threshold_db: 18`, `floor_dbfs: -60`, `min_bars: 2`.

- 18 dB below the typical sung level sits under reverb tails and the backing-vocal bleed Demucs leaves at around −20 to −25 dB. It is a starting point, tuned against the PNG.
- `min_bars: 2` matches T7's lesson (a one-bar dip is a breath) and the waveform experiment's 2-bar minimum.

### The transition

- **Exit A** = `first_bar` of the earliest window with `first_bar > exit_after_bar` (config, 32) and `length ≥ max(min_bars, overlap_bars)`. Exit time = that bar's downbeat.
  - The window must *start* after bar 32. A window already running at bar 32 doesn't count, because its start is not "a sung line just ended".
  - For the adhoc pair the expected exit is around bar 41 or 73. The real number comes from the stem, and it can be compared directly with the user's own pick of bar 73.
- **Entry B** = `downbeat_times[0]` (bar 1). Bar 1 rather than sample 0, so that B's first beat lands where A's bar would have started, and any silence or pre-roll before B's grid is skipped.
- *Alternatives:* B entered after its vocal-free intro, just before its first sung line. Dropped by the user in favour of always entering at the intro, to keep the experiment to one variable: A's exit.

### Rendering

All three outputs load A and B at 48 kHz with `load_canonical`. When `render.match_loudness` is set, B's samples are multiplied by `10^((lufs_a − lufs_b)/20)` (+4.4 dB for the adhoc pair). A peak above 0 dBFS is recorded in the report; it is not limited, so the result is heard honestly.

- **Hard cut:** build a tier-3 `Junction(cue_out=exit_s, cue_in=entry_s, length_bars=0, …)` and call `render_junction` with the full PCM. That is the existing renderer, unchanged.
- **Overlap** (`render.overlap_bars: 2`): `L = transition_span(exit_bar, overlap_bars) = downbeat[exit_bar + overlap_bars] − downbeat[exit_bar]`, i.e. A's own bar lengths, falling back to `overlap_bars · 240 / bpm_a` past the last downbeat. The output is `A[0:exit] ++ (A[exit:exit+L]·cos(πt/2) + B[entry:entry+L]·sin(πt/2)) ++ B[entry+L:]`, with `linear_edge_fade` at A's last sample. Equal-power because the two signals are uncorrelated. No tempo change. Because A's window is at least `overlap_bars` long, A stays vocal-free throughout the overlap.
- **Bass swap** (`render.bass_swap_bars: 16`, `render.crossover_hz: 200`):
  - **Span:** `L` is the same `transition_span` over 16 of A's bars from the exit downbeat (≈ 29.1 s at 132 BPM). The swap point is the downbeat of bar `exit_bar + 8`. If A has fewer than 16 bars after the exit, the bass swap is skipped with a reason and the other two outputs are still written.
  - **Band split:** a 4th-order Butterworth low-pass at `crossover_hz`, run with `sosfiltfilt` (zero-phase, so the two bands stay in time), gives `low`, and `rest = signal − low`. Because the two bands sum back to the original exactly, a band at gain 1 plus the other at gain 1 is the untouched track. The same split is used on A and B. The waveform experiment's `bands.py` uses the same filter family, and `scipy` is already in the environment through `librosa`.
  - **Gains over the span** (t from 0 to 1, swap at t = 0.5):
    - `A.low = 1` before the swap and `0` after
    - `B.low = 0` before and `1` after
    - `B.rest = sin(π·t)` over the first half, then `1`
    - `A.rest = 1` over the first half, then `cos(π·(t − 0.5))` down to `0`

    Each half is an equal-power fade. The swap is a hard step on the downbeat, as a DJ does it with the EQ knobs, with a 5 ms linear ramp so it doesn't click.
  - **Output:** `A[0:exit] ++ (A_span·gains + B_span·gains) ++ B[entry+L:]`, which is the same total length as the other two outputs.
  - *Alternatives:* an ever-rising B volume across the whole 16 bars with no bass step, i.e. a long crossfade. Rejected: the design doc lists the full crossfade as the worst failure mode, and the bass step is the point of the technique. Separate EQ curves per band (low/mid/high) were also rejected as more knobs than the experiment needs.
- **Drift:** `drift_ms = L · |1 − bpm_b/bpm_a| · 1000`. For 132.0 vs 130.7 BPM this is about 36 ms over the 2-bar overlap, an audible flam on kicks but short, and about 287 ms over the 16-bar bass swap, clearly off the beat by its end. Both are reported. This pair is a test of the mechanics, not a fair hearing of the bass swap, which needs a same-BPM pair (see Risks).
- *Alternative:* adding an overlap strategy to `render/transition_renderer`. Rejected for now, because that needs a production spec change and is premature before the experiment shows overlaps are worth it.

### Outputs

```
src/experiments/vocal_free_windows/outputs/<pair_id>/
  A_vocal_lane.png
  windows.json             # A's per-bar levels, threshold, windows; exit and entry
  transition_cut.wav
  transition_overlap.wav
  transition_bass_swap.wav
  summary.md
```

`ground_truth.yaml` (committed template):

```yaml
pairs:
  Y7G-tYRzwYY__KxCjVIFxZNo:   # Subha Hone Na De -> Lat Lag Gayee
    cut:     {rating: null, note: null}   # 1-5
    overlap: {rating: null, note: null}
    bass_swap: {rating: null, note: null}
```

## Risks / Trade-offs

- [Demucs leaks backing vocals or choir into the stem, or misses ad-libs, so windows open or close in the wrong place] → The PNG shows level, threshold and exit side by side. `threshold_db` and `min_bars` are tunable, and listening to the output is the final check.
- [B's intro has vocals (some film songs open with a sung line or a spoken hook), so the overlap stacks two voices or the cut lands on a voice] → Accepted by the simplification. The hard-cut output is still clean on A's side, and the listening rating records it. Separating B is the obvious follow-up if this keeps happening.
- [`torch` + `demucs` 4.0.1 vs the Python 3.11 / numpy 2 stack] → Task 1.1 checks install and a separation smoke test first. The fix is pinning `torch`/`torchaudio` in the experiments group, not a design change.
- [A sings continuously past bar 32 with no 2-bar gap] → The run fails with that reason (spec). Lowering `exit_after_bar` or `min_bars` is a config change.
- [Tempo drift (no tempo matching): small in the 2-bar overlap, but about 287 ms over the 16-bar bass swap on the adhoc pair] → Accepted, per the same-BPM assumption. The drift is reported for each output, so a bad bass swap can be told apart from a bad technique. A same-BPM pair, such as Zingaat → Munni Badnaam Hui at 130.0/130.0, can be run with `--a/--b` for a fair bass-swap hearing.
- [The 16-bar bass swap runs past A's vocal-free window and past B's intro] → Accepted. A's vocal over B's instrumental intro is normal practice. If B's intro is shorter than 8 bars, B's vocal may come in while A's mids and highs are still fading, which the rating will catch. `bass_swap_bars: 8` is a one-line change.
- [Summing two full-band tracks during the bass swap's first half lifts the peak] → The peak of each output is reported. No limiter.
- [LUFS gain pushes B above 0 dBFS] → The peak is reported, not hidden. A limiter is out of scope.
- [Bar grid errors (downbeat_confidence is low on this material: 0.02 / 0.04)] → The cut lands on the extractor's downbeat, which the hard-cut output exposes by ear. This is the same dependency as every other module, not something new.

## Migration Plan

None. Sandbox only. To remove it, delete `src/experiments/vocal_free_windows/`, its tests, `.cache/vocal_free_windows/`, and the `demucs` line in the experiments group.

## Findings

First live run, 2026-10-20, on Subha Hone Na De → Lat Lag Gayee:

- **Windows (A):** bars 1–3, 14–15, 17–23 and 57–63 at an 18 dB threshold (cutoff −31.1 dBFS). The exit was **bar 57 (1:42)**, the start of the first window after bar 32. That isn't the user's earlier pick of bar 73, and the stem shows A singing continuously from bar 64 through bar 73.
- **Transition style:** by ear, the user preferred the **bass swap**, which "is what I was expecting". The hard cut and the 2-bar overlap were ranked below it. This held despite the bass swap's ~288 ms tempo drift on this pair (132.0 vs 130.7 BPM).
- **Loudness:** matching B to A by raising B (+4.4 dB) put every output's peak above 0 dBFS (+4.1 / +4.1 / +5.6 dBFS). This is unresolved, see the pause note in the apply session.
