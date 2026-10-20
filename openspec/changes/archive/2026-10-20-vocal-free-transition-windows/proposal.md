# Proposal

## Why

The rule a DJ follows for a fast megamix transition is "never cut a singer off". The pipeline can't follow it yet. The only vocal signal is `vocal_band_energy` (energy between 300 Hz and 3 kHz, which also picks up guitars, synths, horns and dhol), and it only enters as a soft cost on cue points chosen for other reasons (T7: a cut landed mid-phrase). This sandbox experiment tests the direct version of the rule in its simplest form: separate track A's vocals, leave A at its first real vocal gap after its opening, go into B's intro, and listen to the result.

## What Changes

- New sandbox experiment `src/experiments/vocal_free_windows/`, with its own `config.yaml` and a CLI runner, laid out like `waveform_llm_transition`. Nothing in production imports it.
- **Input: one pair of tracks, A → B.** The default and the live test input is the adhoc pair from `waveform_llm_transition/outputs/adhoc`: Subha Hone Na De → Lat Lag Gayee (`Y7G-tYRzwYY__KxCjVIFxZNo`). Any other pair can be passed on the command line.
- **Vocal-free windows in A:** a pretrained source-separation model (Demucs) isolates A's vocals. The stem is cached by `(content_hash, separator_version)` and measured per bar on the cached feature extractor's downbeat grid. A window is a run of at least a configured number of bars below a threshold set relative to A's own vocal level, so one-bar breaths don't count.
- **The one transition this experiment makes:**
  - **Exit A:** the downbeat of the first bar of A's first vocal-free window that starts after bar 32.
  - **Entry B:** B's intro, i.e. B from its first downbeat (bar 1).
  - If A has no such window, the run fails with that reason. There is no fallback.
- **Output: one full-length mixed track per transition style.** A plays from its start to the exit, then B plays from its intro to its end:
  - `transition_cut.wav`: a hard cut on the downbeat, through the existing tier-3 `cut_on_the_one` renderer.
  - `transition_overlap.wav`: a short equal-power overlap of a configured number of bars, which stays inside A's vocal-free window. This is rendered by an experiment-local mixer, because `render/` has no overlap strategy yet.
  - `transition_bass_swap.wav`: a DJ-style bass swap that takes a configured number of bars to finish (16 by default). It starts at the same exit point and runs as follows:
    - The first half brings in B's mids and highs with B's bass cut.
    - On the downbeat halfway through, A's bass and B's bass swap.
    - The second half fades out A's mids and highs.
    - Unlike the 2-bar overlap, this one runs past A's vocal-free window, so A's vocal may sound over B's intro.
    - It is rendered by the same experiment-local mixer.
  - B is gain-matched to A by integrated LUFS in all versions.
  - **No tempo matching.** The pair is assumed to be at about the same BPM; a later module placed before this one will make sure only such pairs come in. The drift is reported, not corrected.
- **Report and checks:** `summary.md` lists A's windows, the exit bar and time, the BPM drift across the overlap and the bass swap, the gain applied to B, and the output paths. A PNG of A's vocal level shows the threshold, windows and exit for checking by eye. `ground_truth.yaml` takes a 1–5 rating and a note per output file.
- Adds `demucs` (which pulls in `torch`) to the `experiments` dependency group only.

## Capabilities

### New Capabilities

- `vocal-free-transition-experiment`: a sandbox experiment that, for one pair of tracks A → B, finds vocal-free windows in A from its separated vocal stem, leaves A at the first window after bar 32, enters B at its intro, and renders full-length mixed tracks with a hard-cut, a short-overlap, and a bass-swap transition. Results are informative only and never feed the production pipeline.

### Modified Capabilities

None. `feature_extractor` and `render/transition_renderer` are used as they are. If vocal-free windows prove useful, a separate change will amend `feature_extractor`/`cue_derivation` to produce them as cue candidates.

## Impact

- **New code:** `src/experiments/vocal_free_windows/` and `tests/experiments/vocal_free_windows/`.
- **Dependencies:** `demucs` (plus `torch`) in the `experiments` group of `pyproject.toml`. The production install is unchanged.
- **Disk:** about 50 MB of 16-bit vocal stem WAV per separated track under `.cache/vocal_free_windows/` (git-ignored, like the rest of `.cache/`), plus three full-length WAVs per pair under the git-ignored `outputs/`.
- **Runtime:** separation of A takes tens of seconds, once per track thanks to the cache. B is never separated. Re-runs only redo the windows, exit, renders and report.
- **Existing code read, not changed:** `ingestion.feature_extractor.cache` / `loader`, `render.transition_renderer` (`cut_on_the_one`, `linear_edge_fade`), and `render.playlist_renderer.writer`.
