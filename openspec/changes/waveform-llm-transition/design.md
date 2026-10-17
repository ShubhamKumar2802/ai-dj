# Design

## Context

See proposal.md for motivation. The pieces this experiment needs already exist:

- **Features:** `ingestion/feature_extractor.get_or_extract_features(path, FeatureExtractorConfig())` returns cached `RawFeatures`. The fields used here are `duration`, `bpm`, `lufs_integrated` and `downbeat_times`. All four tracks are already cached. `load_canonical(path)` returns 48 kHz stereo float32 PCM.
- **LLM:** `common/llm_service.get_llm_service()` accepts a `MultimodalRequest(prompt, images=[ImageInput(source="base64", data=..., mime_type="image/png")])` plus a pydantic output schema, and caches responses on disk. The repo's configured model (`config.yaml` → `llm_service`) is used unless the experiment config overrides `model` per request.
- **Render:** `render/transition_renderer.render_junction(junction, audio_a, audio_b)` with `strategy_tier=3` (`cut_on_the_one`) splices A from sample 0 to `cue_out` onto B from `cue_in` to its end, with 5 ms edge fades. It asserts 48 kHz.
- **Layout to follow:** `experiments/lyrics_sourcing`: a `config.yaml` where unknown keys are errors, a `run_experiment.py` that swaps `sys.path[0]` for `src/` and `chdir`s to the repo root, and an `outputs/` folder inside the experiment.

## Goals / Non-Goals

**Goals:**
- Images a vision model can read precisely: fixed scale, labelled bars, nothing ambiguous.
- Keep every deterministic step (bar → time, tiling, scoring) a pure function that can be unit-tested without audio or an LLM.
- Re-runs are cheap: features and LLM responses are already cached, and only images, previews and the report are regenerated.

**Non-Goals:**
- Rendering any technique other than a hard cut.
- Section labelling, or comparing against `structure_llm.py` or `cue_derivation` cues.
- Time-stretching. The Rock Tha Party → Marjaani pair is ~2% apart, which is acceptable for a cut.
- Running on the gold set or batches beyond the configured pairs.

## Decisions

### Module layout
```
src/experiments/waveform_llm_transition/
  config.yaml          pairs, tile/band/preview params, model override, paths
  config.py            load + validate config (unknown keys -> error)
  schema.py            pydantic: TransitionAnswer (LLM output); dataclasses for results
  bars.py              bar<->time, mm:ss parse/format, nearest-bar   (pure)
  bands.py             3-band envelopes from PCM                      (pure numpy/scipy)
  tiles.py             tile windows; matplotlib drawing of one tile
  prompt.py            prompt text + request builder
  preview.py           build Junction, trim PCM, call render_junction, write WAV
  scoring.py           ground_truth.yaml -> per-pair bar errors        (pure)
  report.py            summary.md
  run_experiment.py    CLI: for each pair -> features, tiles, LLM, preview, score, report
  ground_truth.yaml    user-filled; template committed with blanks
  outputs/<pair_id>/   tiles/*.png, request_meta.json, answer.json, preview.wav, summary.md
```
`pair_id` = `<A youtube id>__<B youtube id>`, taken from the `[...]` suffix in the filename, with the file stem as a fallback.

### Band split: Butterworth crossover via `scipy.signal.sosfiltfilt`
4th-order low-pass below 200 Hz, band-pass from 200 Hz to 2.5 kHz, and high-pass above 2.5 kHz, applied to mono-summed 48 kHz PCM. All cutoffs come from config. The envelope is the RMS level per pixel column, smoothed over `smooth_beats` beats (default 1, using the track's BPM) and converted to dB. Lane height maps a `range_db` window (default 24 dB) below the pair's anchor level (see "Shared scale") onto the lane, bottom to top; anything quieter draws empty.
*Changed 2026-10-16* from the original peak envelope with square-root compression. On these heavily limited film-song masters (-9 to -10 LUFS), peak levels sit near the ceiling for the whole song, and beat-level jitter (one spike per kick) was larger than the steps between sections, so tiles looked the same from start to end. Measured as the spread of per-bar lane height (p90–p10, fraction of the lane): Munni Badnaam Hui low/mid/high went from 0.23/0.20/0.22 to 0.48/0.35/0.50, Rock Tha Party from 0.21/0.14/0.12 to 0.44/0.22/0.23, and pixel-to-pixel jitter fell about 8× (0.07 → 0.009). Rock Tha Party's low-end thinning from about bar 86, which the model misread as "full through bar 89", is clearly visible only in the new rendering.
*Alternative:* keep the peak envelope (the DJ-software look). Rejected: it shows almost no section contrast on loud masters. *Alternative:* an 18 dB window. Rejected: with a shared scale it squashes the quieter track of a pair (Marjaani's low lane median height 0.07, vs 0.29 at 24 dB).
*Alternative:* sum STFT bins per band. It's simpler, but it smears transients across the frame length, and transients are exactly what show where a beat drops in.

### Shared scale within a pair
Each band's dB scale is anchored at that band's maximum beat-smoothed level across **both** tracks of the pair, so lane heights are comparable between A and B and nothing clips.
*Changed 2026-10-16* from the 98th percentile, which was meant to stop one transient from setting the scale. Beat smoothing already removes isolated transients, and the percentile clipped 3.5–4.5% of the louder track's columns flat at full height, in its loudest sections, exactly where sections need comparing. The true maximum is only 1.6–3.4 dB above the 98th percentile, so anchoring there costs about a tenth of the 24 dB lane. Pixels-per-second is fixed by config (default tile 60 s → 1500 px, 25 px/s), and the final tile of a track is drawn at the same px/s with empty space rather than being stretched.
*Alternative:* normalise each track separately. That's rejected because it hides that one track's drop is bigger.

### Tiles
Windows start at `k * (tile_s - overlap_s)` and run until one covers the end (defaults 60 s / 8 s). Each tile is a matplotlib figure with three stacked lanes (fixed lane colours: low = blue, mid = orange, high = grey), a header line, and two label rows below the axis: bar numbers every 2 bars and mm:ss every 5 s. Each lane is drawn mirrored about its centre line, the level shown as the distance from the centre in both directions. *Changed back 2026-10-17* from a bottom-up fill (task 4.4): the bottom-up lanes read as "only the upper half is visible" when checked against the audio, and the mirrored form is the familiar DJ-software look; the cost is half the lane height per side. Gridlines are drawn at every downbeat (thin, light) and every 4th bar (stronger), on all lanes. The figure is saved as PNG at a fixed size. Track A's tiles are sent first, then B's, in time order. Each image is preceded in the prompt by a line naming it, e.g. "A tile 2/4 (1:00–2:05)".
*Alternative:* one long image per track. It's rejected because vision models downscale wide images, which loses the per-bar detail.

### One call per pair; answer in bars
Prompt structure:
1. The task: this transition is one junction in a megamix that plays only about 30–90 s of each song, around its most recognisable, highest-energy part. Choose where to leave A (right after a strong section ends, on a 4-bar line, not in its closing bars) and where to enter B (at or just before its strongest section; skipping B's intro is normal; bar 1 only if B opens at full energy).
2. How to read the images.
3. Both tracks' facts.
4. The tiles.
5. The required JSON.

Prompt `waveform_transition_v2` (2026-10-16) adds, from the v1 runs: the megamix framing above (v1's "club-style transition" led both Gemma and Nemotron to play A to its end and start B at bar 1); a reading note that film songs rarely have beat-free intros/outros, so the end of the file is a fade, not a mix-out point; that each m:ss is the time printed under the chosen bar's line, read after picking the bar; and that when a change in the lanes falls between bar lines, the bar line just before it is chosen. The prompt still never uses the word "hook" or gives any cue estimate. v2 is a separate template file (`prompts/waveform_transition_v2.txt`); v1 stays on disk for comparison.

Prompt `waveform_transition_v3` (2026-10-16) changes only the lane-reading note, to match the new rendering: lane height is that band's loudness on a 24 dB scale shared by both tracks, drawn up from the bottom of the lane; an empty lane means the band is more than 24 dB below the pair's loudest level. v3 is `prompts/waveform_transition_v3.txt`; v1 and v2 stay on disk.

Prompt `waveform_transition_v4` (2026-10-17) changes only that note's drawing description, for the return to mirrored lanes: each lane is drawn symmetrically about its centre line, and an empty lane shows only the centre line. v4 is `prompts/waveform_transition_v4.txt`; earlier versions stay on disk.

Prompt `waveform_transition_v5` (2026-10-17) targets where A is left and how closely the tiles are read, from the v2–v4 runs:
- **First exit, not a later one.** A has been playing from its start; leave at the first point where A's opening full-energy section ends (its first breakdown or dip after the beat is in), not a later one. v4 only ruled out A's closing bars, so any later section end qualified, and the model drifted late (Subha Hone Na De: bar 73 under v3, bar 129 under v4; the user's own pick is bar 73).
- **Every tile, every change.** `notes_a`/`notes_b` must list every visible change in any lane with the bar where it starts, working through every tile in order, before the exit and entry are chosen; sections usually last 8–32 bars, so a 40+ bar span means changes were missed. v2–v4 notes summarised Munni bars 17–160, Rock Tha Party bars 4–92 and Subha bars 17–128 as single sections, missing visible breaks (Subha's bars 73–81 among them).
- **Leave before thinning.** If A's energy starts to thin, leave on the darker 4-bar line before the thinning begins (Rock Tha Party thins from about bar 86; the model chose 89, then 93).
- **Recognisable means repeated.** The most recognisable part is a section whose shape comes back two or three times, not just the loudest stretch.
- **Check B's next 16 bars.** If B's LOW lane drops out or B breaks down within 16 bars of the entry, enter later, after the break (Lat Lag Gayee bar 5 under v3 ran into a bass gap at bars 13–19).

v5 is `prompts/waveform_transition_v5.txt`; earlier versions stay on disk.

Prompt `waveform_transition_v6` (2026-10-17) defines what counts as a section change: a breakdown, dip or drop must last at least 2 bars; dips shorter than a bar (drum fills, stops) are ignored, both when choosing A's first exit, in B's 16-bar entry check, and in the notes. v5 read a sub-beat LOW pinch just before Subha Hone Na De bar 41 as "the first LOW drop" and exited at bar 37, 36 bars before the user's bar 73, which is the first 2+ bar breakdown (bars 73–81). v6 is `prompts/waveform_transition_v6.txt`; earlier versions stay on disk.

Answers so far (exit A bar → entry B bar, technique):

| Pair | v1, Gemma `gemma-4-31b-it` | v1, Nemotron, no `max_tokens` | v1, Nemotron, `max_tokens` 32768 | v2, Nemotron | v3, Nemotron |
|---|---|---|---|---|---|
| Rock Tha Party → Marjaani (95 / 114 bars) | 93 → 1, filter_fade 8 | 95 → 1, filter_fade 4 | 93 → 5, cut | 89 → 5, cut | 93 → 5, cut |
| Zingaat → Munni Badnaam Hui (125 / 160 bars) | — | 121 → 1, cut | 121 → 1, cut | 97 → 17, cut | 97 → 17, cut |

One-off pair from the gold set, run with a separate `--config` (not one of the configured pairs): Subha Hone Na De → Lat Lag Gayee (149 / 135 bars): v3 73 → 5, bass_swap 2; v4 129 → 19, bass_swap 2; v5 37 → 5, cut (a direct replay of the same v5 request, outside the runner and not saved, gave 73 → 19; one v5 run returned no answer). The user marks A's exit at bar 73 (2:11). The saved v5 run's notes also missed Lat Lag Gayee's LOW gap at bars 13–19 that the v4 run and the replay both listed, so its 16-bar entry check passed on a misreading.

The pydantic schema `TransitionAnswer` has these fields:
- `exit_bar_a: int`, `exit_time_a: str`
- `entry_bar_b: int`, `entry_time_b: str`
- `technique: Literal["cut","bass_swap","echo_out","filter_fade","other"]`, `length_bars: int`
- `reasoning: str`
- `notes_a: str`, `notes_b: str`

The bar number is what gets used. The mm:ss value is only a cross-check, and a disagreement larger than one bar is recorded (spec).
*Alternative:* answer in seconds and snap to the nearest downbeat. It's rejected because reading positions off the axis is the weakest part of the setup, and labelled bars avoid it.

### Preview via the existing renderer, on trimmed PCM
`cut_on_the_one` always plays A from sample 0. To get a short clip, `preview.py` slices A's PCM to `[cue_out − pre_s, cue_out]` and B's to `[cue_in, cue_in + post_s]`, then builds a `Junction` with:
- `cue_out = pre_s` and `cue_in = 0`
- `strategy_tier=3`, `length_bars=0`, `ramp_bars=0`
- `bar_seconds = 240 / bpm_a` (4 beats per bar at A's tempo)
- `rate_a = rate_b = 1.0`, gains 0 dB, `envelopes=[]`

The result is written as a 48 kHz WAV with `soundfile`. If the window would run past either track's edge, it is clipped to what exists.
*Alternative:* render the full mix and slice the output. It works, but needlessly decodes and copies whole tracks.

### Scoring
For each marked time, take the nearest downbeat index (+1) and compute `llm_bar − human_bar` as a signed error in bars. The summary also lists the absolute error in seconds. The rating and note are passed through. A missing file or entry gives "not marked".

### Config and model
The experiment's `config.yaml` holds:
- `pairs: [{a: <path>, b: <path>}]`
- `bands: {low_hz: 200, high_hz: 2500, filter_order: 4, range_db: 24, smooth_beats: 1}`
- `tiles: {tile_s: 60, overlap_s: 8, px_per_s: 25, height_px: 600}`
- `preview: {pre_s: 20, post_s: 20}`
- `llm: {model: null, temperature: 0.2, max_tokens: 32768, timeout_s: 300}`
- `outputs_dir`

`model: null` means the repo's configured `llm_service` model. It must be vision-capable. The run fails fast with a clear error if the provider rejects images.

`max_tokens` caps the model's whole output, including any reasoning ("thinking") tokens, not just the JSON answer. A reasoning model that spends the whole budget thinking returns no answer, which surfaces as a validation failure for that pair. `null` sends no cap, so the provider's own limit applies (131k output tokens for `nvidia/nemotron-3.5-super-vl:free`). The default of 32768 leaves room for reasoning over 9–11 images while still bounding a runaway call.

`timeout_s` is the per-request time limit, replacing the 180 s previously hard-coded in `prompt.py`. Nemotron took 128–173 s per pair on prompt v2.

### Testing
`tests/experiments/waveform_llm_transition/` covers:
- **bars.py:** bar ↔ time, mm:ss parsing, nearest bar, out-of-range handling
- **Tile windows:** coverage and overlap
- **bands.py:** on synthetic sines (100 Hz → low lane dominant, 1 kHz → mid, 6 kHz → high)
- **Shared normalisation**
- **Preview Junction building and PCM trimming:** on synthetic arrays
- **scoring.py**

Tile drawing gets one smoke test (it writes a PNG of the expected size). Nothing calls the LLM or reads `music/`.

## Risks / Trade-offs

- [Beat tracker off by a beat or half-tempo on a track] → Bar lines would be drawn wrong, and the cut would land off the beat. Mitigation: it's audible in the preview, and the summary prints `downbeat_confidence`. Both pairs were picked partly for their better confidence (0.49–0.66).
- [The configured model (currently OpenRouter's `nvidia/nemotron-3.5-super-vl:free`) reads images poorly or downsizes them] → Mitigation: the model can be overridden in the experiment config without code changes; tile size and px/s are also config.
- [The LLM ignores the bar labels and guesses] → The mm:ss cross-check shows this as recorded disagreements.
- [Hard cut hides a good choice whose technique needs a blend] → Accepted (decision: option 2). The suggested technique is saved for the user to judge.
- [Answers vary between runs at temperature 0.2: pair 1 gave 95→1, then 93→5] → Accepted for a go/no-go sniff test. Before trusting a single answer, repeat each pair several times with the cache disabled.
- [The free tier sometimes returns no answer at all (`expected TransitionAnswer, got NoneType`), even well inside `max_tokens`] → Seen once on v5 (the replay of the same request used 14k of 32k tokens and answered). The pair is reported as failed; re-run it. `llm_service` does not retry this case.
- [Two pairs is a tiny sample] → Accepted: this is a go/no-go sniff test, not a benchmark.

## Open Questions

- Which vision model to settle on, if the default performs poorly. It can be changed in config without touching specs or tasks.
