# Tasks

## 1. Setup

- [x] 1.1 Add `demucs` to the `experiments` dependency group with `uv add --group experiments demucs`. Verify that `uv run --group experiments python -c "import demucs, torch; print(torch.backends.mps.is_available())"` succeeds. If it fails, pin `torch`/`torchaudio` in the experiments group (design.md Risks) and re-check. Also verify `uv run pytest` still passes without the experiments group
- [x] 1.2 Create `src/experiments/vocal_free_windows/` (with `__init__.py`) and `tests/experiments/vocal_free_windows/` (with `__init__.py`). Verify `uv run pytest tests/experiments/vocal_free_windows` collects with no errors

## 2. Config

- [x] 2.1 Write `config.yaml` with:
  - the adhoc pair as default: A `music/gold-set/＂Subha Hone Na De Full Song＂… [Y7G-tYRzwYY].mp3`, B `music/Lat Lag Gayee Lyrical - Race 2 … [KxCjVIFxZNo].mp3`, exact paths copied from `music/`
  - `separator`: htdemucs, shifts 1, overlap 0.25, device auto, cache_dir `.cache/vocal_free_windows`
  - `windows`: threshold_db 18, floor_dbfs -60, min_bars 2
  - `exit_after_bar: 32`
  - `render`: overlap_bars 2, bass_swap_bars 16, crossover_hz 200, match_loudness true
  - `outputs_dir` and `ground_truth`

  Implement `config.py` with every field required and unknown keys rejected, `bass_swap_bars` required to be even, plus `track_id`/`pair_id` (YouTube-id suffix, as in the waveform experiment) and a `separator_version` property. Verify with tests: a valid config loads, an unknown key raises, a 15-bar bass swap is rejected naming the field (spec "Odd length"), the default pair's `pair_id` is `Y7G-tYRzwYY__KxCjVIFxZNo`, and `separator_version` changes when model, shifts or overlap change

## 3. Levels, windows, exit (pure)

- [x] 3.1 Implement `levels.py`: per-bar linear RMS of the mono-summed stem over each bar's `[start_time, end_time)`, clipped to the stem length. Verify with tests on synthetic PCM: a silent stem gives all zeros with one entry per bar (spec "Silent stem", "Series length"), and a bar holding a sine reads higher than its silent neighbours
- [x] 3.2 Implement the windows in `windows.py`: dB conversion, the p95 reference, the `max(reference − threshold_db, floor_dbfs)` cutoff, and runs of at least `min_bars`, returned as 1-based first/last bars with start/end times. Verify with tests for the spec scenarios "Breath between lines", "Instrumental break" and "Relative threshold"
- [x] 3.3 Implement the exit pick in `windows.py`. Verify with tests for the spec scenarios "First window after bar 32" (bar 41), "Window that started before bar 33" (bar 73), "Window too short for the overlap" and "No usable window", plus a test that every overlap bar of A lies inside the exit window (spec "A stays vocal-free in the overlap")

## 4. Separation and stem cache

- [x] 4.1 Implement `stem_cache.py`: a key from `(content_hash, separator_version)`, a 16-bit stereo 48 kHz WAV written atomically, and a cache-hit read. Verify with tests using a fake separator callable for the spec scenarios "Re-run on the same audio", "Separator changed" and "Renamed file"
- [x] 4.2 Implement `separation.py` as the only module importing `demucs`/`torch`, with imports inside the function: 48 kHz → model rate, `apply_model`, the `vocals` source, back to 48 kHz, and the device picked by `auto`. Verify with a test, skipped when `demucs` isn't importable, that 5 s of synthetic stereo comes back as stereo at 48 kHz with the same sample count. Also verify by separating Subha Hone Na De once and listening to its stem WAV

## 5. Mixing

- [x] 5.1 Implement the hard cut in `mix.py` through `render_junction` with a tier-3 `Junction` on full PCM, with B entering at its first downbeat, plus the B gain from LUFS. Verify with tests on synthetic PCM: the output length matches the spec "Cut output length" arithmetic, B's audio starts from its first downbeat (spec "Entry time"), and with matching on, B's samples are scaled by `10^((lufs_a − lufs_b)/20)` while A's are unchanged (spec "Quieter B")
- [x] 5.2 Implement the overlap in `mix.py`: `transition_span` from A's downbeats, an equal-power crossfade, B continuing to its end, and `drift_ms`. Verify with tests on synthetic PCM: the output length and A's last non-zero sample match the spec "Overlap output length" arithmetic, the gains at the midpoint are both ≈ 0.707, and `drift_ms` for 132.0/130.7 BPM is ≈ 36 ms over 2 bars and ≈ 287 ms over 16 (spec "Drift reported")
- [x] 5.3 Implement `bass_swap.py`: the zero-phase Butterworth split at `crossover_hz` with `rest = signal − low`, the gain curves from design.md, the hard bass step with a 5 ms ramp on the halfway downbeat, and the skip-with-reason when A has too few bars left. Verify with tests on synthetic PCM, using a 60 Hz sine for "low" and a 2 kHz sine for "rest", different for A and B:
  - the split sums back to the input within 1e-6
  - output length and A's last non-zero sample match the spec "Bass-swap output length" arithmetic
  - before the swap downbeat only A's 60 Hz is present in the low band, and after it only B's (spec "Swap on the halfway downbeat")
  - B's rest is silent at the span start and A's rest is silent at the span end
  - an exit 10 bars from A's end skips the bass swap with a reason while cut and overlap still render (spec "Not enough of A left")

## 6. Image and report

- [x] 6.1 Implement `plot.py`, A's PNG showing the stem level in dB, threshold, shaded windows, the bar-32 line and the exit bar, with bar and mm:ss labels. Verify with a smoke test that a synthetic track writes a PNG, and by viewing the real image by eye
- [x] 6.2 Implement `report.py` and a committed `ground_truth.yaml` template with blank cut/overlap/bass_swap rating and note for the adhoc pair. Verify with tests: a success summary lists A's windows, the exit and entry, both drift values, gain, each output's peak, and the output and image paths; a skipped bass swap shows its reason; a failed run shows the reason; and an unrated output shows as not rated (spec "Not rated yet")

## 7. Runner and live run

- [x] 7.1 Implement `run_experiment.py` following the waveform experiment's CLI pattern (`sys.path[0]` set to `src/`, change directory to the repo root, `--config`, optional `--a`/`--b`). Flow: features for A and B → A's stem (cached) → levels → windows → exit → image → cut, overlap and bass-swap outputs → `windows.json` → `summary.md`. A missing path stops the run before separation. Document the run command in the module docstring. Verify `--help` works without separation running, and verify with a test that a missing `--a` path exits with an error naming it (spec "Missing audio file")
- [x] 7.2 Live run on the adhoc pair: `uv run --group experiments python src/experiments/vocal_free_windows/run_experiment.py`. Verify `outputs/Y7G-tYRzwYY__KxCjVIFxZNo/` contains `A_vocal_lane.png`, `windows.json`, `transition_cut.wav`, `transition_overlap.wav`, `transition_bass_swap.wav` and `summary.md`. Re-run and confirm from the logs that no separation ran
- [x] 7.3 Check sandbox isolation: verify `grep -rn "vocal_free_windows" src --include='*.py'` finds nothing outside the experiment itself, then run `uv run ruff check .` and `uv run pytest` and verify both pass

## 8. Listening check

- [x] 8.1 Listen to all three output tracks around the transition, and in the bass swap listen for the bass step on the halfway downbeat, and check on the PNG that the exit sits in a window you also hear as vocal-free. Compare the exit bar with your own bar-73 pick. Fill `ground_truth.yaml`'s cut/overlap/bass_swap rating and note, re-run, and verify the report shows them. Record findings (whether the window was right, cut vs overlap vs bass swap, how much the drift hurt the bass swap, whether B's intro worked, any threshold tuning) in a new `## Findings` section at the end of design.md

## Workflow follow-up

- If vocal-free exits prove useful, open a separate change that amends `feature_extractor`/`cue_derivation` to emit window edges as cue candidates, and consider separating B to pick its entry and an overlap strategy in `render/transition_renderer`.
- Archive this change with `/opsx:archive` once its tasks are done.
