# Proposal

## Why

The repo can find beats, bars and phrase blocks deterministically, but it cannot yet tell which part of a song is a good place to leave or enter it — `hook_in`/`hook_exit` are an energy-plus-vocals stand-in (`overview.md` T8), and the earlier number-based LLM experiment (`llm_camelot_sequencer/structure_llm.py`) needed heavy after-the-fact validation. DJs make this call by eye from a 3-band waveform. This sandbox experiment tests whether a vision-capable LLM, shown the same kind of picture, can pick a good transition between two tracks.

## What Changes

- New sandbox experiment `src/experiments/waveform_llm_transition/` (nothing in production imports it), with its own `config.yaml` and a CLI runner, following the `lyrics_sourcing` experiment's layout.
- Renders a DJ-style 3-band (low / mid / high) waveform for each track as stacked lanes, split into fixed-scale overlapping image tiles. Every tile has a header (track name, BPM, duration, integrated LUFS, tile index and time range), bar-number and mm:ss labels under the x-axis, and bar / 4-bar gridlines. Both tracks of a pair share the same pixels-per-second and the same height scale.
- The only measured facts given to the LLM are duration, BPM, integrated LUFS and the bar grid, all taken from the cached `feature_extractor` output. It is not given the key, phrase grid, or `cue_derivation`'s entry/exit guesses.
- Makes **one LLM call per pair**, through `common/llm_service`, with both tracks' tiles. It returns the exit bar in A, the entry bar in B (each with an mm:ss cross-check), a suggested technique and length, its reasoning, and free-text notes on what it sees in each track.
- Renders a short **audio preview** of each transition as a hard cut on the downbeat (strategy tier 3, `cut_on_the_one`) at the LLM's chosen bars. The suggested technique is recorded, not rendered.
- **Light accuracy check:** the user hand-marks their own exit/entry points per pair plus a 1–5 listening rating and note in `ground_truth.yaml`. A report shows the LLM's distance from the user's points in bars, alongside the rating.
- Runs on two fixed pairs from `music/` (not the gold set): Rock Tha Party → Marjaani, and Zingaat → Munni Badnaam Hui.
- Adds `matplotlib` to the `experiments` dependency group.

## Capabilities

### New Capabilities
- `waveform-transition-experiment`: The sandbox experiment's observable behaviour: what images it produces, what the LLM is given and must return, the preview audio it renders, and how it scores against hand-marked points.

### Modified Capabilities
None.

## Impact

- **New code:** `src/experiments/waveform_llm_transition/` and tests under `tests/experiments/waveform_llm_transition/` (pure functions only; no audio files, no LLM calls).
- **Reuses, unchanged:**
  - `ingestion/feature_extractor` (`get_or_extract_features`, `load_canonical`)
  - `common/llm_service` (`MultimodalRequest`, `ImageInput`)
  - `render/transition_renderer` (`render_junction` with tier 3)
- **Dependencies:** `matplotlib` added to the `experiments` group in `pyproject.toml`. No production dependency changes.
- **Outputs:** written under the experiment's `outputs/` folder: PNG tiles, the LLM response JSON, preview WAVs, and a summary report.
- **External:** two LLM requests per run, cached by `llm_service`.
