# Tasks

## 1. Setup

- [x] 1.1 Add `matplotlib` to the `experiments` dependency group with `uv add --group experiments matplotlib`, and verify `uv run --group experiments python -c "import matplotlib"` succeeds
- [x] 1.2 Create `src/experiments/waveform_llm_transition/` (with `__init__.py`) and `tests/experiments/waveform_llm_transition/` (with `__init__.py`), and verify `uv run pytest tests/experiments/waveform_llm_transition` collects with no errors

## 2. Config and schemas

- [x] 2.1 Write `config.yaml` with the two pairs (Rock Tha Party → Marjaani, Zingaat → Munni Badnaam Hui, by their `music/` paths) and the band/tile/preview/llm/outputs settings from design.md. Implement `config.py`, which loads the file and rejects unknown keys. Verify with tests: a valid config loads, an unknown key raises, and a missing pair path is reported per pair
- [x] 2.2 Implement `schema.py`: the `TransitionAnswer` pydantic model (fields and technique enum as in design.md) plus result dataclasses. Verify with a test that a sample JSON answer parses and an unknown technique is rejected

## 3. Bars and time (pure)

- [x] 3.1 Implement `bars.py`:
  - bar N → start time, counting from 1 against the downbeats
  - mm:ss parsing and formatting
  - nearest bar to a time
  - range check returning a clear error string

  Verify with tests covering the spec's "Bar to time", "Bar beyond track end" and "Bar and time disagree" scenarios

## 4. Waveform images

- [x] 4.1 Implement `bands.py`: a Butterworth crossover via `sosfiltfilt` into low/mid/high, peak envelope per pixel column with square-root compression, and normalisation shared across the pair. Verify with tests on synthetic 100 Hz / 1 kHz / 6 kHz sines (the matching lane dominates) and a shared-scale test (a louder track keeps the taller lane)
- [x] 4.2 Implement the tile window calculation in `tiles.py`. Verify with tests for the spec's "Tiling a track" scenario: full coverage, the 8 s overlap, and the last tile kept at the same px/s
- [x] 4.3 Implement tile drawing in `tiles.py`:
  - three stacked lanes
  - the header (A/B label, name, BPM, duration, LUFS, tile index and range)
  - bar-number and mm:ss label rows
  - bar and 4-bar gridlines

  Verify with a smoke test that a synthetic track writes a PNG of the configured pixel size, and by viewing one real tile by eye
- [x] 4.4 Switch the envelope to the design.md rendering: RMS per pixel column, smoothed over `bands.smooth_beats` beats from the track's BPM, in dB, with a `bands.range_db` window anchored at each band's pair-wide 98th percentile; lanes filled bottom-up. Add `range_db` and `smooth_beats` to `config.yaml` and `BandsConfig`. Verify with tests: the synthetic sines still land in the matching lane, a track whose low band is twice as energetic draws a taller low lane, a passage more than `range_db` below the anchor draws empty, the tile smoke test still writes the configured PNG size, and by viewing one real tile by eye
- [x] 4.5 Anchor each band's dB window at the pair-wide maximum of the beat-smoothed level instead of the 98th percentile (design.md "Shared scale within a pair"). Verify with tests: no column of either track exceeds full lane height and only the loudest column reaches it, the existing shared-scale tests still pass, and by re-rendering the Munni tile 2 (bars 29–61) to confirm the MID lane no longer flat-tops
- [x] 4.6 Draw lanes mirrored about their centre line again (design.md "Tiles"), keeping the dB scale and smoothing. Verify with the tile smoke test (configured PNG size) and by re-rendering one real tile by eye

## 5. LLM request

- [x] 5.1 Implement `prompt.py`: prompt text (task, how to read the images, per-track facts, the required JSON) plus a `MultimodalRequest` builder with A's tiles then B's, each labelled. Verify with tests that the request has all tiles in order, contains duration/BPM/LUFS for both tracks, and contains no key or cue-point values
- [x] 5.2 Add `llm.max_tokens` (`int | None`, default 32768 per design.md) to `config.yaml` and `LlmConfig`, and pass it into the `MultimodalRequest` built in `prompt.py`. Verify with tests: the request carries the configured value, `null` leaves `max_tokens` unset, and a non-positive value is rejected
- [x] 5.3 Write prompt v2 as a new template `prompts/waveform_transition_v2.txt` (`# prompt_version: waveform_transition_v2`) with the changes design.md lists, and point `prompt.py` at it; keep v1's file unchanged. Verify with tests: the request's version is `waveform_transition_v2`, the prompt contains the megamix framing, and the existing no-key/no-cue test (including no "hook") still passes
- [x] 5.4 Write prompt v3 as a new template `prompts/waveform_transition_v3.txt` (`# prompt_version: waveform_transition_v3`): v2 with only the lane-reading note changed as design.md describes; point `prompt.py` at it and keep v1/v2 unchanged. Verify with tests: the version is `waveform_transition_v3`, the prompt describes the 24 dB shared scale, and the no-key/no-cue test still passes
- [x] 5.5 Add `llm.timeout_s` (positive number, 300 in `config.yaml`) to `LlmConfig` and pass it into the `MultimodalRequest` in place of the hard-coded 180. Verify with tests: the request carries the configured value, and a non-positive value is rejected
- [x] 5.6 Write prompt v4 as a new template `prompts/waveform_transition_v4.txt` (`# prompt_version: waveform_transition_v4`): v3 with the lane note describing mirrored lanes, as design.md describes; point `prompt.py` at it and keep earlier versions unchanged. Verify with tests: the version is `waveform_transition_v4`, the prompt describes the mirrored drawing and the shared dB scale, and the no-key/no-cue test still passes
- [x] 5.7 Write prompt v5 as a new template `prompts/waveform_transition_v5.txt` (`# prompt_version: waveform_transition_v5`) with the changes design.md lists; point `prompt.py` at it and keep earlier versions unchanged. Add the Subha Hone Na De → Lat Lag Gayee pair to `ground_truth.yaml` with `exit_a: "2:11"` (bar 73). Verify with tests: the version is `waveform_transition_v5`, the prompt contains the first-exit rule, the every-tile notes rule and the 16-bar entry check, and the no-key/no-cue test still passes
- [x] 5.8 Write prompt v6 as a new template `prompts/waveform_transition_v6.txt` (`# prompt_version: waveform_transition_v6`): v5 plus the 2-bar minimum for section changes, applied to A's first exit, B's 16-bar entry check and the notes, as design.md describes; point `prompt.py` at it and keep earlier versions unchanged. Verify with tests: the version is `waveform_transition_v6`, the prompt states the 2-bar minimum and that sub-bar dips are ignored, and the no-key/no-cue test still passes

## 6. Preview and scoring

- [x] 6.1 Implement `preview.py`: trim the PCM to the pre/post window (clipped at track edges), build a tier-3 `Junction`, call `render_junction`, and write a 48 kHz WAV. Verify with a test on synthetic PCM that the output length equals pre_s + post_s and the samples come from the expected regions of A and B (spec "Preview window")
- [x] 6.2 Implement `scoring.py` and a committed `ground_truth.yaml` template with blank entries for both pairs. Verify with tests for the "Scored pair" scenario (signed bar error) and "No ground truth yet" (not marked)

## 7. Runner and report

- [x] 7.1 Implement `report.py`, writing a per-run `summary.md`. It covers, per pair: bars and times, technique and length, flagged disagreements, `downbeat_confidence`, the preview path, and the score and rating, or the failure reason. Verify with a test rendering a summary for one succeeded and one failed pair
- [x] 7.2 Implement `run_experiment.py`, following the `lyrics_sourcing` CLI pattern (`sys.path[0]` set to `src/`, `chdir` to the repo root, `--config`). Each pair is processed independently: features → tiles → LLM → validate → preview → score → report. Document the run command in the module docstring, and verify `--help` works
- [ ] 7.3 Run `uv run --group experiments python src/experiments/waveform_llm_transition/run_experiment.py` on both pairs. Verify that each pair's `outputs/<pair_id>/` contains tiles, `answer.json`, `preview.wav` and that `summary.md` is written. Listen to both previews once to confirm the cut lands on a downbeat
- [x] 7.4 Run `uv run ruff check .` and `uv run pytest tests/experiments/waveform_llm_transition`, and verify both pass
- [ ] 7.5 Re-run both pairs with prompt v2. Compare the exit/entry bars with the v1 answers in design.md's table, and listen to both previews
- [ ] 7.6 Re-run both pairs with the new rendering and prompt v3. Compare against the v1/v2 answers in design.md's table, and listen to both previews
- [ ] 7.7 Re-run the Subha Hone Na De → Lat Lag Gayee pair with prompt v5. Compare against its v3/v4 answers and the user's bar 73, check that the notes list the bars 73–81 breakdown and no span longer than 32 bars, and listen to the preview. Re-running the configured pairs is deferred
- [ ] 7.8 Re-run the Subha Hone Na De → Lat Lag Gayee pair with prompt v6. Compare the exit with the user's bar 73 (scored by `ground_truth.yaml`) and the earlier answers, check the notes ignore the bar-41 fill and list B's bars 13–19 gap, and listen to the preview

## Workflow follow-up

- User fills `ground_truth.yaml` (exit/entry by ear, rating 1–5, note), then re-runs to produce the scored summary. The LLM responses are cached, so no new LLM calls are made.
- Archive the change with `/opsx:archive` once the results have been reviewed.
