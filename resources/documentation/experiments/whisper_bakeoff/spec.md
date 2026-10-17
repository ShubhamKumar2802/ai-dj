# experiments/whisper_bakeoff — Spec

**Status: draft, awaiting approval.** No code exists under `src/experiments/whisper_bakeoff/` yet.

Part of the pipeline documentation set: this experiment exists to answer the open
questions in [`../../pipeline/04_transcription.md`](../../pipeline/04_transcription.md)
(§4 **Q4**, and partly **Q1**, **Q2**) before that proposal is promoted to a real
`ingestion/transcription` spec. Related: [`../../pipeline/00_pipeline_map.md`](../../pipeline/00_pipeline_map.md),
[`../../pipeline/06_experiments_sandbox.md`](../../pipeline/06_experiments_sandbox.md),
[`../../pipeline/05_song_structure.md`](../../pipeline/05_song_structure.md) (the consumer
of transcription's output).

---

## 0. Purpose and invariant

`04_transcription.md` proposes local Whisper-family ASR to give the pipeline one signal it
lacks: **a repeated lyric line marks the chorus/hook**. Its own Q4 says the whole value
proposition is unvalidated on this repertoire (Hindi/Urdu, English, and code-switched
Bollywood, *sung over a full backing track*), and that this should be measured before
real spec work proceeds. This experiment does that measurement.

It answers four concrete questions, each of which becomes a decision in the eventual
`transcription` spec:

1. **Model** — `large-v3` or `turbo`?
2. **Input** — the raw mix, or a vocal stem separated first?
3. **Language handling** — auto-detect, or force `hi`?
4. **Go / no-go** — does the best configuration clear a usable bar at all? If not,
   `04`'s transcription proposal is parked, not built.

**Invariant.** This experiment is a standalone sandbox, in the same sense as
`src/experiments/llm_camelot_sequencer/` (`06_experiments_sandbox.md` §0): nothing under
`src/` outside `src/experiments/whisper_bakeoff/` imports it, it adds no field to `Track`
or any production contract, and it is not part of the automated test suite's real-audio
path. Results are **informative, not authoritative** — they gate whether a real spec is
worth writing; they don't replace one.

## 1. Non-goals

- Not the `transcription` module. No `TranscriptionResult` schema, no cache-key axis
  (`transcription_version`), no orchestrator wiring — those belong to the real spec.
- Not a full-track transcript quality audit. Scoring is restricted to hand-labeled
  windows (§4); nobody is going to hand-transcribe 5 full songs.
- No fine-tuning and no decode-parameter sweep (§3.3 fixes them). Fine-tuned Hinglish
  models are listed as a stretch axis only (§9 Q5).
- No lyric *correctness* claim beyond the labeled windows, and no judgment of whether
  repeated-line detection would improve `hook_in`/`hook_exit`. That is `05`'s question.

## 2. Hardware and dependencies

Target: an Apple Silicon Mac mini with 32 GB unified memory. `large-v3` needs ~10 GB, so
memory is not a constraint; the full grid (§3.1) is a background job, not an interactive
one.

New dependencies go in a **separate `uv` dependency group** so the production install
stays lean and Apple-only packages never leak into it:

```
uv add --group experiments mlx-whisper demucs jiwer indic-transliteration
```

| Package | Used for |
|---|---|
| `mlx-whisper` | Whisper inference on Apple Silicon (MLX). Apple-only, which is a further reason for its own group. |
| `demucs` | Vocal separation (`htdemucs`, two-stem `vocals`). Pulls in PyTorch. |
| `jiwer` | WER/CER computation. |
| `indic-transliteration` | Devanagari → Roman, so hypotheses can be compared against Roman-typed references (§5.2). |

Existing dependencies reused: `librosa` (16 kHz resample), `soundfile`,
`ingestion.feature_extractor.loader.load_canonical` (decode).

## 3. Experiment design

### 3.1 The grid

Three axes, full factorial — 2 × 2 × 2 = **8 configurations**, run over **5 tracks** =
**40 runs**:

| Axis | Values |
|---|---|
| `model` | `large-v3`, `turbo` |
| `source` | `mix` (full decoded track), `vocals` (Demucs vocal stem of the same track) |
| `language` | `auto` (Whisper's own detection), `hi` (forced) |

`.en` models are excluded outright (the corpus is Hindi/Urdu-dominant); `medium` is
excluded because `turbo` dominates it on both speed and quality.

### 3.2 Track sample

Five tracks from `music/`, chosen **by the user** (this spec does not pick them), covering:

- 2 × Hindi-dominant
- 2 × code-switched Hindi/English
- 1 × English-dominant

Each must have at least one clearly audible, repeated chorus (the thing being tested).

### 3.3 Fixed decode parameters

Held constant across every run and **recorded in the results file** so a run is
reproducible. These are deliberately not swept:

```
word_timestamps            = True
condition_on_previous_text = False   # limits hallucination cascading through
                                     #   instrumental sections (04 Q1)
temperature                = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)   # Whisper default fallback ladder
compression_ratio_threshold, logprob_threshold, no_speech_threshold = Whisper defaults
task                       = "transcribe"   # never "translate"
```

The `no_speech_threshold` default is a known-weak defence on music; whether to tighten it
is a finding to report, not a knob this experiment turns.

## 4. Ground truth: the references manifest

The user hand-labels ground truth by ear (the same "cue points found by ear, typed into
JSON" workflow as the walking skeleton). One JSON file, `references.json`, path passed on
the command line; a committed `references.example.json` shows the shape.

```
References:
  version : int                    # manifest schema version, currently 1
  tracks  : list[TrackReference]

TrackReference:
  track_path          : str        # path to the audio file, relative to the repo root
  language_profile    : "hindi" | "code_switched" | "english"
  chorus_windows      : list[Window]   # >= 1; every audible occurrence of the chorus
  chorus_text         : str        # what is sung in a chorus occurrence, typed in Roman
                                   #   script (see §5.2); same text is expected in each window
  instrumental_windows: list[Window]   # >= 0; stretches with NO vocals at all
                                       #   (used for the hallucination metric)

Window:
  start : float                    # seconds from file start, float64 (design-v3 D20)
  end   : float
```

**Validation** (`references.py`, fails fast with a clear message rather than scoring
garbage): `start < end` for every window; windows within `[0, duration]`; `chorus_windows`
non-empty; `chorus_text` non-empty after normalization; no window in `instrumental_windows`
overlaps any in `chorus_windows`; the audio file exists.

## 5. Scoring

All scoring is a pure function of `(hypothesis Transcript, TrackReference)` — no model, no
audio — so it is unit-testable with synthetic fixtures.

### 5.1 Windowed hypothesis extraction

A hypothesis word belongs to a window if the **midpoint** of its `[start, end]` falls inside
`[window.start, window.end)`. The window's hypothesis text is those words joined in time
order. Word-level timestamps are therefore required (§3.3).

### 5.2 Normalization

Sung Hindi has no canonical romanization (`kya`/`kyaa`, `dil`/`dhil`), and Whisper may emit
Devanagari, Roman, or Urdu script, possibly mixed within one song (`04`'s risk list). Both
sides are normalized to one comparable form before scoring:

1. Unicode NFKC; lowercase.
2. Devanagari → Roman via `indic-transliteration` (ITRANS → plain-ASCII fold).
3. Strip punctuation; collapse whitespace.
4. **Urdu (Perso-Arabic) script is not transliterated in v1.** If a hypothesis contains it,
   it is left as-is, will score badly, and is **counted and reported** as
   `urdu_script_words` rather than hidden. Whether that justifies real Urdu handling is
   a finding (§9 Q3).

### 5.3 Metrics

| Metric | Definition | Role |
|---|---|---|
| `chorus_cer` | Character error rate, hypothesis vs `chorus_text`, per chorus window; **median across windows and tracks** | **Primary.** CER, not WER, because romanization variance makes word-level match unfairly harsh. |
| `chorus_wer` | Same, word level | Secondary; reported, not decisive. |
| `repeat_agreement` | For a track with ≥ 2 chorus windows: mean pairwise `1 − CER` between the windows' *hypothesis* texts (hypothesis vs hypothesis, no reference) | **The downstream-relevant metric.** Repeated-line detection only needs the model to be *consistently* right or wrong across occurrences, not perfect. |
| `hallucination_rate` | Words emitted inside `instrumental_windows` per minute of instrumental audio | Directly answers `04` Q1. Lower is better; the reference value is 0. |
| `urdu_script_words` | Count of Perso-Arabic-script words in hypotheses | Diagnostic (§5.2). |
| `detected_language` | Whisper's detected language, per track | Diagnostic for the `auto` vs `hi` axis. |
| `rtf` | Wall-clock ÷ audio duration, transcription only; Demucs time reported separately | Cost. |
| `peak_rss_mb` | Peak resident memory of the process | Cost; sanity check on the 32 GB assumption. |

### 5.4 Decision rule (fixed before running)

Stated up front so the results can't be rationalized afterwards. **The numeric thresholds
are unvalidated guesses**, chosen to be sensible starting points, and should be reviewed
by the user at approval time:

1. A configuration is **usable** iff median `chorus_cer ≤ 0.35` **and** median
   `repeat_agreement ≥ 0.70` **and** `hallucination_rate` is not worse than the median of
   the other configurations by more than 2×.
2. Among usable configurations, **pick the lowest median `chorus_cer`**. If two are within
   **0.02 absolute** CER, pick the faster (`rtf`, including Demucs time if it applies).
3. **If no configuration is usable, the outcome is "no-go"**: `04`'s transcription proposal
   is parked and `05`'s labeling proceeds on segmentation + LLM alone. That is a valid,
   useful result, not a failure of the experiment.
4. The `mix` vs `vocals` decision and the `auto` vs `hi` decision are made **per the same
   rule**, holding the winning model fixed (marginal comparison), and reported with the
   full table so the user can override.

## 6. Pipeline

```
references.json ──► validate ──┐
                               ▼
per track:  load_canonical ─► to_mono_16k ─► [mix]
                        │                       │
                        └─► demucs (cached) ─► [vocals]
                                                │
per config (model × source × language):         ▼
                                       mlx_whisper.transcribe
                                                │
                                          Transcript (words + timestamps)
                                                │
                                   normalize ─► score (§5) ─► RunResult
                                                │
all runs ─────────────────────────────────────► report (results.json + report.md)
```

Decode goes through the pipeline's own `load_canonical` (48 kHz stereo float32, design-v3
**D25**), then is downmixed and resampled to 16 kHz mono in-process. This is deliberate: it
gives a data point for `04` **Q2** (should transcription share the canonical decode?) —
if results are good on canonical-derived audio, sharing the decode is validated.

**Caching.** Two caches under `.cache/whisper_bakeoff/` (already covered by the repo's
`.cache/` gitignore rule):

- Demucs stems: keyed on `(content_hash, demucs_model_id)`. Separation is the slowest step
  and is identical across the 4 configs sharing a `source`.
- Transcripts: keyed on `(content_hash, run_config_id)`, where `run_config_id` hashes
  `{model_id, source, language, decode_params, mlx_whisper_version}`. Scoring is re-run
  from cache so metric/normalization changes cost nothing.

Both follow the project's cache-key rule: **content hash, never filename**.

**Failure isolation.** One failing run (Demucs error, model OOM, empty transcript) is
recorded as a `RunResult` with `error` set and excluded from medians (and *listed* in the
report), never aborting the batch — the same philosophy as `orchestrator`'s
`IngestionFailure`.

## 7. Outputs

Written to `src/experiments/whisper_bakeoff/outputs/` (gitignored — the repo already ignores
`src/experiments/**/outputs/`):

| File | Contents |
|---|---|
| `results.json` | One `RunResult` per (track, config): all §5.3 metrics, the full run config incl. decode params, library versions, and per-window hypothesis text for manual inspection. |
| `report.md` | Per-config table (medians), per-track breakdown, the §5.4 decision applied mechanically with the verdict stated, and a list of errored runs. |

`report.md`'s conclusions are then copied by hand into `04_transcription.md` (Q4 resolved,
§3.2 model choice) — this experiment never edits specs itself.

## 8. Pinned file layout

```
src/experiments/whisper_bakeoff/
    __init__.py
    config.py            # Axes, RunConfig, fixed decode params (§3.3), model-id constants
    references.py        # References/TrackReference/Window models + validate() (§4)
    audio.py             # to_mono_16k(); separate_vocals() with the Demucs stem cache
    transcribe.py        # run_whisper(audio, RunConfig) -> Transcript; transcript cache
    normalize.py         # normalize_text() (§5.2)
    scoring.py           # windowed extraction + all §5.3 metrics; pure functions
    report.py            # build_report(results) -> report.md text; apply decision rule (§5.4)
    run_bakeoff.py       # CLI entry point (§8.1)
    references.example.json

tests/experiments/whisper_bakeoff/
    __init__.py          # ancestors already have one (see tests/README.md)
    conftest.py          # synthetic Transcript / TrackReference builders
    test_references.py   # validation failures (bad window, overlap, empty text)
    test_normalize.py    # Devanagari -> Roman, punctuation, Urdu-script passthrough
    test_scoring.py      # midpoint windowing, CER/WER, repeat_agreement, hallucination_rate
    test_report.py       # decision rule: usable filter, tie-break, no-go verdict
```

Modules that call a real model or Demucs (`audio.py`'s separation, `transcribe.py`) are
**not unit-tested**, matching `llm_camelot_sequencer`'s precedent; everything that is a pure
function of data (`references`, `normalize`, `scoring`, `report`) is. This keeps the
metadata-only testability property intact for the parts where a bug would silently corrupt
the conclusion.

### 8.1 CLI

```
uv run --group experiments python src/experiments/whisper_bakeoff/run_bakeoff.py \
    <references.json> [--models large-v3,turbo] [--sources mix,vocals] \
    [--languages auto,hi] [--rescore-only]
```

Defaults run the full §3.1 grid. `--rescore-only` skips all model/Demucs work and rebuilds
`results.json`/`report.md` from the caches (used after changing normalization or scoring).

### 8.2 Public types (sketch)

```
Word:       text: str, start: float, end: float, probability: float | None
Transcript: language: str | None, words: list[Word]      # words flat, time-ordered

RunConfig:  model: "large-v3" | "turbo"
            source: "mix" | "vocals"
            language: "auto" | "hi"

RunResult:  track_path: str, config: RunConfig,
            chorus_cer: float | None, chorus_wer: float | None,
            repeat_agreement: float | None,        # None if the track has < 2 chorus windows
            hallucination_rate: float | None,      # None if the track has no instrumental windows
            urdu_script_words: int, detected_language: str | None,
            rtf: float, demucs_seconds: float | None, peak_rss_mb: float,
            error: str | None
```

## 9. Open questions

- **Q1 — MLX model repositories.** The expected sources are the `mlx-community`
  conversions of `large-v3` and `large-v3-turbo`. Exact repo IDs and whether they match
  OpenAI's current weights must be confirmed when implementing. Pin the resolved IDs in
  `config.py` and record them in `results.json`.
- **Q2 — Demucs on Apple Silicon.** Whether `demucs`'s PyTorch install and MPS backend work
  cleanly under `uv` on this machine is unverified. CPU fallback is acceptable (the
  grid is small) but slow; if it doesn't install, the `vocals` axis is dropped and the
  experiment answers only questions 1, 3, 4.
- **Q3 — Urdu-script output.** If hypotheses contain meaningful Perso-Arabic text, v1's
  no-transliteration choice makes scores pessimistic. The `urdu_script_words` count
  tells us how much; if it's large, add a transliteration step and amend this spec.
- **Q4 — Reference labeling effort.** Someone has to find chorus windows and type the
  lyrics by ear for 5 tracks. That's the user's action, and the experiment can't start
  without it. Decide whether one chorus occurrence typed once (as specified) is enough,
  or whether verses should be added for a fuller picture.
- **Q5 — Fine-tuned models (stretch).** [Trelis's Hinglish `large-v3` fine-tune](https://huggingface.co/Trelis/whisper-hinglish-preview)
  and the [ARTPARK Hindi fine-tune](https://huggingface.co/ARTPARK-IISc/whisper-large-v3-vaani-hindi)
  are trained on speech, not singing. If the base models are marginal in the first run,
  add `model` values for them as a second-round experiment (a spec amendment, since it
  changes the grid).
- **Q6 — Forced-language granularity.** `language="hi"` applies to the whole file; songs
  that switch to English mid-verse may get mangled by it. The `auto` vs `hi` comparison
  measures whether that matters on this sample, but a per-segment strategy isn't tested.

## 10. Rejected alternatives

| Alternative | Why not |
|---|---|
| `faster-whisper` | No Metal backend; runs CPU-only on Mac. (`04_transcription.md` §3.2 currently names it — it should be updated to reflect this experiment's runtime choice once results are in.) |
| `whisper.cpp` | Viable (Metal/Core ML) but slower than MLX in the benchmarks found, needs a C++ build or bindings, and adds no accuracy. Kept as the fallback if `mlx-whisper` proves unstable. |
| WER as the primary metric | Romanized Hindi has no canonical spelling, so word-level match punishes correct output. CER is the primary; WER is reported for reference. |
| Scoring whole-track transcripts | No ground truth exists and nobody will hand-transcribe five songs. Windowed scoring against hand-labeled choruses is the tractable version. |
| Sweeping decode parameters | Multiplies the grid for marginal signal. Fixed once (§3.3); revisit only if results are borderline. |
| Picking the sample tracks automatically | The point is representative coverage of the repertoire's hard cases; that's a judgment call, and only the user knows which tracks have clear choruses. |
| `medium` and `.en` models | Dominated by `turbo`, and unusable on Hindi/Urdu, respectively. |
