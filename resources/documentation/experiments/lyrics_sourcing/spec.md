# experiments/lyrics_sourcing — Spec

**Status: draft, awaiting approval.** No code exists under `src/experiments/lyrics_sourcing/` yet.

Part of the pipeline documentation set. This experiment is an **end-to-end, single-track
pipeline** that tests an alternative to
[`../../pipeline/04_transcription.md`](../../pipeline/04_transcription.md) and an early version
of [`../../pipeline/05_song_structure.md`](../../pipeline/05_song_structure.md)'s labeling step:

1. **ingest** a track from a YouTube link (existing downloader),
2. fetch its **time-synced lyrics** from the same link,
3. **time-match** them against our audio, using a local Whisper transcript as the validator,
   and as the source of truth if no usable lyrics are fetched,
4. pull **all metadata** our built analysis modules produce,
5. flatten everything into one **time-first TOON file**, one row per second,
6. send it to a **local LLM on Ollama**, which labels the song's structure.

Sibling experiment: [`../whisper_bakeoff/spec.md`](../whisper_bakeoff/spec.md), which measures
how good the Whisper fallback is. Related: [`../../acquisition/youtube_downloader/spec.md`](../../acquisition/youtube_downloader/spec.md),
[`../../ingestion/feature_extractor/spec.md`](../../ingestion/feature_extractor/spec.md),
[`../../ingestion/cue_derivation/spec.md`](../../ingestion/cue_derivation/spec.md),
[`../../common/llm_service/spec.md`](../../common/llm_service/spec.md),
[`../../pipeline/06_experiments_sandbox.md`](../../pipeline/06_experiments_sandbox.md).

---

## 0. Purpose and invariants

`04` exists for one signal: **a repeated lyric line marks the chorus/hook**. Transcribing sung
Hindi/Urdu/code-switched Bollywood is hard and unvalidated (`04` Q4). Human-written synced lyrics
often already exist, with correct text. Their weakness is **timing**: they are timed to the
studio/album recording, while our download is often a music-video edit with extra material in
front. The two sources cover each other's weak spots:

| | Fetched synced lyrics | Local Whisper transcript |
|---|---|---|
| Text | Correct (human-written) | Error-prone on this repertoire |
| Timing | Relative to *some* recording, maybe not ours | Mechanically tied to *our* audio |
| Availability | Unknown coverage | Always (given the audio) |

Validating timing needs far less transcript accuracy than using the transcript *as* lyrics:
anchoring a few dozen lines to fuzzy matches is enough to estimate an offset.

The experiment answers, for the tracks the user runs it on:

1. Can synced lyrics be fetched from the YouTube link (and LRCLIB as a fallback)?
2. Do they line up with our audio, with an offset, or not at all?
3. Given timed lyrics plus our per-second metadata, can a **local** LLM produce a plausible
   section labeling and hook window, and how does its hook compare to `cue_derivation`'s
   energy-based `hook_in`/`hook_exit` proxy?

**Invariant 1: sandbox.** Same rules as `whisper_bakeoff` §0. Nothing under `src/` outside
`src/experiments/lyrics_sourcing/` imports it. It adds no field to `Track`, `DownloadedTrack`,
`RawFeatures` or any production contract, and it modifies no production module (including
`common/llm_service`). It may *import* production code. Results are informative, not
authoritative.

**Invariant 2: swappable steps.** Each of the six steps (plus transcription, which step 3 depends
on) lives in its own sub-directory with an interface, one or more implementations, and a factory.
The pipeline only ever talks to the interface. Which implementation runs is chosen in
`config.yaml`, never in code. Swapping an implementation means adding a file and a registry line,
then changing one `impl:` value (§3).

**Invariant 3: every step's output is on disk.** Each step writes its output under
`outputs/<video_id>/` before the next step starts, and the pipeline can resume from any step
by reloading earlier outputs (§4.8). This is what makes swapping one step cheap.

## 1. Non-goals

- Not the production `transcription` or `structure_labeler` module. No production schema, cache
  axis or orchestrator wiring.
- Not a coverage study. It runs on one or a few tracks the user picks (videos known to have
  lyrics). A multi-track coverage run with a go/no-go rule is future work (§9 Q6).
- Not a Whisper model comparison: the configuration is fixed (§4.3), and that choice belongs to
  `whisper_bakeoff`.
- No forced alignment of plain (untimed) lyrics, no piecewise offsets (§9 Q3), no auto-generated
  YouTube captions (§10), and no Musixmatch/scraping.
- No change to planning or render. The LLM's output is written to a file and read by a human.

## 2. Dependencies and environment

New Python dependencies go in the shared **`experiments` dependency group** (the same group
`whisper_bakeoff` uses), never the production install:

```
uv add --group experiments mlx-whisper ytmusicapi httpx rapidfuzz indic-transliteration
```

| Package | Used for |
|---|---|
| `mlx-whisper` | Local transcription on Apple Silicon (§4.3). |
| `ytmusicapi` | YouTube Music watch-playlist → timed lyrics by video ID (§4.2). Unofficial, unauthenticated. |
| `httpx` | LRCLIB HTTP API (§4.2). |
| `rapidfuzz` | Fuzzy line-to-transcript matching (§4.4). |
| `indic-transliteration` | Devanagari → Roman, so lyrics and transcript compare in one script (§4.4). |

Reused: `yt-dlp`, `pyyaml`, `numpy`, `soundfile`, `librosa`,
`acquisition.youtube_downloader`, `ingestion.feature_extractor`, `ingestion.cue_derivation`,
`common.llm_service`.

**TOON is encoded in-house** (`steps/timeline/toon.py`, §4.6). The Python TOON packages are
immature: the PyPI `toon-format` name is a reservation, and the official `toon-python` is a
git-only beta. We only ever *encode* one fixed shape, which is a few dozen lines.

**Ollama (outside the repo):**
```
OLLAMA_MODELS="$PWD/models/ollama" OLLAMA_CONTEXT_LENGTH=16384 ollama serve   # terminal 1
OLLAMA_MODELS="$PWD/models/ollama" ollama pull qwen3:14b                       # terminal 2
```
- **All model weights live in the repo-root `models/` directory** (a sibling of `src/`,
  gitignored). Whisper weights go in `models/whisper/<repo-name>/` (§4.3). Ollama weights go in
  `models/ollama/`, which works only because the *server* is started with `OLLAMA_MODELS`
  pointing there: Ollama's server owns its model store, so the experiment can't redirect it.
  A server started without that variable uses `~/.ollama/models`.
- **The model must support tool calling.** `llm_service` hard-codes
  `with_structured_output(..., method="function_calling")` (its spec §7). `qwen3:14b` is the
  default: tool-capable, multilingual, about 9 GB, fits the 32 GB target. `gemma3` has no tool
  support in Ollama, so it's unusable here.
- **The context length is set on the server.** Ollama's OpenAI-compatible `/v1` endpoint can't set
  `num_ctx` per request, and the default window is far smaller than one track's timeline (about
  8–12k tokens for 4 minutes). The pipeline estimates the prompt's token count and warns when it
  exceeds `llm.context_tokens` (§4.7).

## 3. Folder layout, step pattern, and config

### 3.1 Step pattern

Every step directory has the same three kinds of file:

```
steps/<step>/
    interface.py     # a typing.Protocol: the only thing pipeline.py depends on
    <impl>.py        # one file per implementation; a plain class, __init__(self, cfg: <Step>Config)
    factory.py       # _REGISTRY: dict[str, Callable[[<Step>Config], <Protocol>]]
                     # build(cfg: <Step>Config) -> <Protocol>
```

`build` looks up `cfg.impl` in `_REGISTRY`. An unknown name raises
`ValueError("unknown <step> impl '<name>'; valid: <sorted names>")`. There is no automatic
discovery and no plugin loading: registries are explicit dicts, so a reader can see every option
in one place. This mirrors `youtube_downloader`'s `Downloader` Protocol and `llm_service`'s
provider registry.

### 3.2 `config.yaml`

It lives in the experiment folder and is loaded by `config.py` into a pydantic
`ExperimentConfig` with one sub-model per step. Unknown keys are errors (`extra="forbid"`), so
typos fail at load time. `--config` on the CLI points at an alternative file.

```yaml
outputs_dir: src/experiments/lyrics_sourcing/outputs

ingest:
  impl: youtube
  output_dir: music                  # passed to DownloadConfig.output_dir

lyrics:
  impl: [ytmusic, lrclib]            # fetchers, in priority order; all run (§4.2)
  cache_dir: .cache/lyrics_sourcing/fetch
  lrclib_base_url: https://lrclib.net
  lrclib_user_agent: "ai-dj lyrics_sourcing experiment"
  lrclib_max_candidates: 3
  lrclib_min_interval_s: 1.0

transcribe:
  impl: mlx_whisper
  model: mlx-community/whisper-small-mlx   # smallest viable; see §4.3 for the turbo comparison
  language: null                     # null = auto-detect
  models_dir: models/whisper         # weights downloaded here, never to the HF cache (§4.3)
  cache_dir: .cache/lyrics_sourcing/transcripts

time_match:
  impl: offset_vote
  min_line_chars: 8
  k_candidates: 3
  anchor_min_score: 60
  offset_bin_s: 0.5
  inlier_tolerance_s: 1.5
  min_anchorable_lines: 4
  min_coverage: 0.40
  max_residual_s: 0.60
  zero_offset_tolerance_s: 0.50
  min_transcript_wpm: 20
  max_line_s: 10.0
  write_click_track: true

metadata:
  impl: ingestion_modules

timeline:
  impl: per_second
  serializer: toon                   # toon | json

llm:
  impl: llm_service
  provider: ollama
  model: "qwen3:14b"
  base_url: http://localhost:11434/v1
  api_key: ollama                    # Ollama ignores it; llm_service requires a non-empty value
  temperature: 0.2
  max_tokens: 4096
  request_timeout_s: 600
  max_concurrency: 1
  context_tokens: 16384              # for the token-budget warning only (§4.7)
  cache_enabled: true
  cache_dir: .cache/lyrics_sourcing/llm
```

`lyrics.impl` is a list (the chain). `timeline` has two swappable parts: the builder (`impl`)
and the serializer (`serializer`), each with its own registry. Every other step has a single
`impl`.

### 3.3 Pinned file layout

```
src/experiments/lyrics_sourcing/
    __init__.py
    config.yaml
    config.py                     # ExperimentConfig + per-step config models; load_config(path)
    schema.py                     # every inter-step data contract (§5)
    persistence.py                # save_step / load_step; to_jsonable / from_dict (§4.8)
    pipeline.py                   # STEPS order; run(url, cfg, from_step=None) -> RunSummary (§4.8)
    summary.py                    # build_summary() -> summary.md text (§4.7); pure
    run_experiment.py             # CLI (§6)
    steps/
        __init__.py
        ingest/
            __init__.py  interface.py (TrackIngester)  youtube.py  factory.py
        lyrics/
            __init__.py  interface.py (LyricsFetcher)
            ytmusic.py   lrclib.py   lrc.py   fetch_cache.py   factory.py
        transcribe/
            __init__.py  interface.py (Transcriber)  mlx_whisper.py  factory.py
        time_match/
            __init__.py  interface.py (TimeMatcher)
            offset_vote.py   passthrough.py   normalize.py   align.py   resolve.py
            click_track.py   factory.py
        metadata/
            __init__.py  interface.py (MetadataExtractor)  ingestion_modules.py  factory.py
        timeline/
            __init__.py  interface.py (TimelineBuilder, TimelineSerializer)
            per_second.py   toon.py   json_serializer.py   factory.py
        llm/
            __init__.py  interface.py (StructureLabeler)
            llm_service_labeler.py   ollama_provider.py   validate.py   factory.py
            prompts/structure_labels.txt
    outputs/                      # gitignored (existing src/experiments/**/outputs/ rule)

tests/experiments/lyrics_sourcing/
    __init__.py                   # + every ancestor and sub-dir: test_config.py collides
                                  #   with tests/common/logging's (tests/README.md rule)
    conftest.py                   # fixtures; skips the dir if the experiments group isn't installed
    builders.py                   # synthetic LyricLine / Transcript builders
    test_config.py
    test_persistence.py
    steps/
        test_factories.py
        lyrics/        test_lrc.py  test_ytmusic_parse.py  test_lrclib_parse.py
        time_match/    test_normalize.py  test_align.py  test_resolve.py
        timeline/      test_per_second.py  test_toon.py
        llm/           test_validate.py  test_prompt.py
    fixtures/                     # recorded ytmusic / lrclib JSON payloads (no network in tests)
```

## 4. Steps

### 4.1 Step 1 — `ingest`

```
class TrackIngester(Protocol):
    def ingest(self, url: str) -> IngestedTrack: ...
```

**`youtube`** (`youtube.py`):
1. Calls `acquisition.youtube_downloader.download_tracks([url], DownloadConfig(output_dir=cfg.output_dir))`.
   The downloader's manifest cache makes a repeat download free. A `DownloadFailure` raises
   `StepError("ingest", ...)`.
2. Runs a metadata probe, `yt_dlp.YoutubeDL({"skip_download": True, "quiet": True}).extract_info(url)`,
   for `track`, `artist` (or `creator`), and `album`. `DownloadedTrack` doesn't carry these, and
   widening a production contract for an experiment is out of bounds (Invariant 1).
3. Computes `content_hash` with `ingestion.feature_extractor.content_hash.hash_file`, the same
   hash every production cache uses.

### 4.2 Step 2 — `lyrics`

```
class LyricsFetcher(Protocol):
    source: str                                        # "ytmusic" | "lrclib" | ...
    def fetch(self, track: IngestedTrack) -> list[LyricsCandidate]: ...
```

The step runs **every** fetcher in `lyrics.impl`, in order, even after one succeeds, and
concatenates the candidates. Order is priority, used only by resolution (§4.4.4). A fetcher that
raises is caught and becomes one candidate with `status="error"`, so it never aborts the run.
Results are cached per `(video_id, source, FETCHER_VERSION)` in `lyrics.cache_dir`. `--refetch`
bypasses the cache.

**`ytmusic`** (`ytmusic.py`): works from the video ID alone, so it's the "lyrics from the same
YT link" path.
1. `YTMusic().get_watch_playlist(videoId=video_id)["lyrics"]` gives a browseId. If it's absent,
   the status is `not_found`.
2. `get_lyrics(browseId, timestamps=True)`:
   - `hasTimestamps` gives one `LyricLine` per timed line (`start_time`/`end_time` are ms, so
     divide by 1000), and the status is `synced`.
   - Otherwise the status is `plain_only`, with the text kept.
3. For a music video, YouTube Music may serve lyrics timed to the album-audio counterpart. That
   is exactly what step 3 detects.

The payload-to-candidate mapping is a pure function, `parse_ytmusic_lyrics(payload) -> LyricsCandidate`,
tested on recorded fixtures.

**`lrclib`** (`lrclib.py`): public API, no auth. Every request sends `lrclib_user_agent`, and
requests are spaced at least `lrclib_min_interval_s` apart.
1. If `title`, `artist` and `album` are all known: `GET /api/get?track_name=&artist_name=&album_name=&duration=`.
2. On a miss, or with missing fields: `GET /api/search`.
   - With `track_name=&artist_name=` if title and artist are known.
   - Otherwise with `q=` set to `clean_title(raw_title)`, which strips bracketed text, pipes and the noise
     phrases in `lrclib.py`'s `_NOISE` tuple (`official video`, `full video song`, `lyrical`,
     `full song`, `audio`, `hd`, `4k`).
3. Keep up to `lrclib_max_candidates` results with non-empty `syncedLyrics`. **Duration is not
   used to filter them.** Music-video edits are legitimately longer than album cuts; step 3
   decides.
4. `instrumental: true` results in `status="not_found"`, with `error="instrumental"`.

**`lrc.py`**, a pure parser: `parse_lrc(text) -> list[LyricLine]`.
- A line with several timestamps (`[00:12.00][01:30.00] text`) becomes one `LyricLine` per
  timestamp.
- The `[offset:±ms]` tag is applied. LRC semantics: a positive offset makes lyrics appear
  *earlier*.
- Metadata tags (`[ar:]`, `[ti:]`, `[al:]`, `[length:]`, …) are ignored.
- Lines whose text is empty after stripping are dropped.
- Lines are sorted by `start`, and `end` is set to the next line's `start` (`None` for the last).

### 4.3 Step 3a — `transcribe`

```
class Transcriber(Protocol):
    def transcribe(self, track: IngestedTrack) -> Transcript: ...
```

Always runs, whether or not lyrics were found: it is the validator when they were and the source
of truth when they weren't.

**`mlx_whisper`** (`mlx_whisper.py`):
1. `load_canonical(path)` (48 kHz stereo, design-v3 D25), downmix to mono, then
   `librosa.resample` to 16 kHz float32.
2. **Weights.** `local = models_dir / cfg.model.split("/")[-1]`. If `local` has no
   `config.json`, run `huggingface_hub.snapshot_download(repo_id=cfg.model, local_dir=local)`.
   The local path, never the repo ID, is what gets passed to mlx-whisper, so nothing lands in
   `~/.cache/huggingface`.
3. `mlx_whisper.transcribe(audio, path_or_hf_repo=str(local), language=cfg.language, **DECODE)`
   with the decode parameters fixed to `whisper_bakeoff` §3.3:
   ```
   word_timestamps            = True
   condition_on_previous_text = False
   temperature                = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
   task                       = "transcribe"
   # compression_ratio_threshold, logprob_threshold, no_speech_threshold = Whisper defaults
   ```
4. Cached in `transcribe.cache_dir` on `(content_hash, whisper_config_id)`, where
   `whisper_config_id` is the SHA-256 of `{model, language, DECODE, mlx_whisper.__version__}`.
   Following the project's cache-key rule, the key is the content hash, never the filename.

**Model choice: `small` (244M) is the default, as the smallest model likely to do the job.**
Whisper has two roles here, and they need different amounts of accuracy:
- **Validator** (the main path). This role is forgiving: the offset vote needs only enough
  fuzzy anchors, and a too-sparse transcript gives `unverifiable`, so the fetched lyrics are
  still used (§4.4.4 rule 2). A weak model degrades this role gracefully.
- **Fallback source of truth.** This role is not forgiving: the transcript text becomes the
  lyrics the LLM sees. `small` is expected to be weak here on sung Hindi.

`tiny`/`base` are excluded: they are expected to produce too few anchors on Hindi vocals over a
full mix to validate anything.

**Planned comparison.** After a `small` run, set `transcribe.model` to
`mlx-community/whisper-large-v3-turbo` and rerun with `--from-step transcribe`. Transcripts are
cached per `whisper_config_id`, so both are kept. Compare the two runs' `03_time_match.json`
(verdict, `line_coverage`, `median_abs_residual_s`, `transcript_density_wpm`).
- If `small` reaches the same accept/reject verdict with usable coverage, it stays.
- If not, the default moves to turbo (a config change, recorded here as an amendment).

How good the *fallback* transcript is remains `whisper_bakeoff`'s question. If it picks a
different model, only `config.yaml` changes, and the cache key changes with it. The exact
`mlx-community` repo IDs are confirmed at implementation time (as in `whisper_bakeoff` §9 Q1).

### 4.4 Step 3b — `time_match`

```
class TimeMatcher(Protocol):
    def match(self, track: IngestedTrack, candidates: list[LyricsCandidate],
              transcript: Transcript) -> SyncedLyrics: ...
```

**`offset_vote`** (`offset_vote.py`) wires the three pure modules below together. The click
track (§4.4.5) is written by `pipeline.py` after the step runs, for whichever matcher is
configured, so the `TimeMatcher` interface stays free of file output. **`passthrough`** (`passthrough.py`) takes the first `synced`
candidate unchanged, with verdict `unverifiable` and `offset_applied_s = 0`, or the transcript
if there is no synced candidate. It is a baseline and swap target, and it ignores the transcript
for validation.

#### 4.4.1 Normalization (`normalize.py`)

Applied to lyric text and transcript words alike, the same as `whisper_bakeoff` §5.2:
1. NFKC, then lowercase.
2. Devanagari → Roman (`indic-transliteration`, ITRANS, then an ASCII fold).
3. Strip punctuation and collapse whitespace.

Perso-Arabic script is left as-is and counted (`urdu_script_words`).

#### 4.4.2 Anchoring (`align.py`, pure)

For each synced candidate, for each lyric line with at least `min_line_chars` normalized
characters (shorter lines like "oh oh" match everywhere and carry no timing information):
1. Slide windows over the transcript's flat word list. Window lengths run from `round(0.7n)` to
   `round(1.3n)` words, where `n` is the line's word count, with a minimum of 1.
2. Score each window with `rapidfuzz.fuzz.ratio` (0–100).
3. Keep the top `k_candidates` non-overlapping windows scoring at least `anchor_min_score`. Each
   one's `delta = first_word.start − line.start`.

Several matches are kept per line, not only the best, because chorus lines repeat and a single
best match pairs lines with the wrong occurrence.

#### 4.4.3 Offset vote and verdict (`align.py`, pure)

1. Pool every anchor's `delta`, each weighted by its score. Slide an `offset_bin_s`-wide window
   centred on each delta in turn. The window holding the most weight wins, and the global offset
   `d0` is the weighted mean of the deltas inside it. (A sliding window rather than fixed
   histogram bins, so a true offset sitting on a bin edge isn't split in two.)
2. **Inliers**: per line, the one anchor with `|delta − d0| ≤ inlier_tolerance_s` that is closest
   to `d0`.
3. `drift_slope` is the least-squares slope of `audio_t` against `lyric_t` over the inliers. It
   is a diagnostic only.
4. Verdict, evaluated in this order:
   1. `unverifiable` if `transcript_density_wpm < min_transcript_wpm`.
   2. `rejected` if `anchorable_lines < min_anchorable_lines`, or `line_coverage < min_coverage`,
      or `median_abs_residual_s > max_residual_s`.
   3. `matched` if `|d0| ≤ zero_offset_tolerance_s`.
   4. Otherwise `offset_corrected`.

**All thresholds are unvalidated starting guesses** (§3.2). Tuning them is a config change,
because the decision is recorded in `03_time_match.json` together with the thresholds used.

#### 4.4.4 Resolution (`resolve.py`, pure)

1. **Accepted lyrics win.** Among candidates with verdict `matched` or `offset_corrected`, pick
   the highest `line_coverage`. Ties within 0.05 go to `lyrics.impl` priority order.
   - Shift the lines by `d0` if the verdict is `offset_corrected`.
   - Clamp to `[0, duration]`, and drop and count lines that land wholly outside.
2. **Else, unverifiable lyrics still beat the transcript.** Take the highest-priority
   `unverifiable` candidate, unshifted. The fetch succeeded and there's no evidence it's wrong.
3. **Else, the transcript is the source of truth.** One `LyricSegment` per Whisper segment, with
   `confidence` set to the mean word probability.
   - This includes fetched-but-`rejected` lyrics: timing that contradicts our audio can't locate
     the hook, however correct the text.

Line ends are the next line's start, capped at `start + max_line_s`. The last line ends at
`min(start + max_line_s, duration)`. For lyrics, confidence is the line's inlier anchor score/100
if it had one, else `None`.

#### 4.4.5 Click track (`click_track.py`)

If `write_click_track` is set, write `outputs/<video_id>/clicks.wav`: the track with a 20 ms,
1 kHz click at −12 dBFS mixed in at every resolved segment start. For `offset_corrected`, also
write `clicks_raw.wav` at the *unshifted* times. Listening to it is the quick by-ear check on
whether the timing is right.

### 4.5 Step 4 — `metadata`

```
class MetadataExtractor(Protocol):
    def extract(self, track: IngestedTrack) -> TrackMetadata: ...
```

**`ingestion_modules`**: `raw = get_or_extract_features(track.path, FeatureExtractorConfig())`,
then `cues = derive_cues(raw, CueDerivationConfig())`. These are the same two calls
`orchestrator/worker._ingest_one` makes. They're called directly because there is no public
single-file ingest API and `Track` drops `per_bar_features`/`riser_candidates`, which the
timeline needs. The feature cache makes reruns free. `familiarity_scorer` isn't built, so it
contributes nothing.

### 4.6 Step 5 — `timeline`

```
class TimelineBuilder(Protocol):
    def build(self, track: IngestedTrack, lyrics: SyncedLyrics, meta: TrackMetadata) -> Timeline: ...

class TimelineSerializer(Protocol):
    extension: str                                    # "toon" | "json"
    def serialize(self, timeline: Timeline) -> str: ...
```

**`per_second`** (`per_second.py`, pure). It builds a `Timeline` (§5) with three parts.

**`header`** (scalars):
- `title`, `artist`, `video_id`, `duration`
- `bpm`, `bpm_confidence`, `key`, `key_confidence`
- `lufs_integrated`, `true_peak`
- `structure_template`, `grid_start`, `phrase_length_bars`, `cue_status`
- `lyrics_source`, `lyrics_verdict`, `lyrics_offset_s`

**`rows`**: one `TimelineRow` per integer second `t ∈ [0, floor(duration)]`.
- A second belongs to the bar whose `[start_time, end_time)` contains `t + 0.5`. If no bar does
  (before the first downbeat or after the last), every per-bar column is `None`.
- Per-bar values repeat across the seconds of that bar.
- Scaled columns are min-max normalized per track to `[0, 1]`, rounded to 2 decimals. A constant
  series becomes `0.0`.

| Column | Source |
|---|---|
| `t` | integer second |
| `bar` | bar index |
| `downbeat` | 1 if a downbeat falls in `[t, t+1)` |
| `beats` | count of `beat_times` in `[t, t+1)` |
| `energy_lufs` | `energy_curve[bar]`, 1 decimal |
| `vocal` | `vocal_band_energy[bar]`, scaled |
| `rms`, `low`, `high`, `centroid`, `flux` | `per_bar_features[bar]`: `rms`, `low_band_energy`, `high_band_energy`, `spectral_centroid`, `spectral_flux`, scaled |
| `chroma` | pitch-class name (`C`…`B`) of `argmax(chroma_vector)` |
| `phrase` | `strength` (2 decimals) of a `phrase_grid` boundary in the second, else `None` |
| `cue` | `;`-joined `kind`s of `cue_ins`/`cue_outs` whose `position` falls in the second, else `None` |
| `riser` | 1 if a `riser_candidate` spans the second (`start_time ≤ t < resolution_time`) |
| `lyric` | `;`-joined text of lyric segments *starting* in the second, else `None` |

**`lyrics`**: the full resolved `LyricSegment` list, repeated as its own table. It carries
`start`/`end`/`text` for every line, while `rows.lyric` only marks where lines start, which keeps
rows short.

**`toon`** (`toon.py`, pure) encodes this subset of TOON:
```
title: Abhi Toh Party Shuru Hui Hai
duration: 189.0
...
timeline[190]{t,bar,downbeat,beats,energy_lufs,vocal,rms,low,high,centroid,flux,chroma,phrase,cue,riser,lyric}:
  0,,0,1,,,,,,,,,,,0,
  1,0,1,2,-14.2,0.31,...,C#,0.82,first_downbeat,0,
  ...
lyrics[42]{start,end,text}:
  12.34,15.8,"Abhi toh party shuru hui hai"
```
- **Header:** `key: value` lines in the fixed §5 order.
- **Tables:** `name[N]{f1,f2,...}:`, then one comma-separated row per item, indented 2 spaces.
- **Nulls** are empty fields. Booleans/ints are written bare. Floats are written in shortest
  `repr` form after the rounding above.
- **Quoting:** a string is wrapped in `"..."` (with `"` → `\"` and `\` → `\\`) iff it is empty,
  or contains `,`, `:`, `"`, `\`, a newline, or leading/trailing whitespace, or would parse as a
  number/`true`/`false`/`null`. Newlines inside text become `\n`.

**`json_serializer`** writes `dataclasses.asdict(timeline)` as indented JSON. It's the
comparison baseline, including for the token-count difference.

The step writes `05_timeline.json`, which is always JSON because it's the pipeline's own resume
format, plus `timeline.<extension>` from the configured serializer. The latter is the exact text
step 6 embeds in the prompt.

### 4.7 Step 6 — `llm`

```
class StructureLabeler(Protocol):
    def label(self, timeline: Timeline, serialized: str, serializer: str) -> StructureResult: ...
```

**`llm_service`** (`llm_service_labeler.py`) uses the existing `common/llm_service` with no
changes to it.
1. **Provider.** `ollama_provider.ensure_registered()` calls
   `register_provider("ollama", _build_ollama)` once. `_build_ollama` returns
   `OpenAICompatibleLLMService(base_url=..., api_key=..., model=..., max_concurrency=...,
   request_timeout_s=...)` from the config. External registration is the extension route
   `llm_service` spec §6 allows. It is idempotent: an existing `"ollama"` registration is left
   in place.
2. **Service.** It builds `LLMServiceConfig(provider="ollama", model, base_url, api_key,
   api_key_env_var="OLLAMA_API_KEY", max_concurrency, request_timeout_s, cache_enabled,
   cache_dir)` directly, then calls `get_llm_service(config)`. `load_config` isn't used, so no
   `.env` key is required. `api_key_env_var` is filled only because the field is required; it is
   never read on this path.
3. **Prompt.** `PromptManager(prompts_dir=<this dir>/prompts).render("structure_labels.txt",
   timeline=serialized, duration=..., column_guide=...)`.
   - The template explains each column (a fixed `column_guide` string built in
     `llm_service_labeler.py` from the §4.6 table).
   - It asks for section labels built from timeline evidence, especially repeated lyric lines.
   - It says boundaries must be integer seconds taken from row `t` values.
   - The first line carries `# prompt_version: 1`.
4. **Token budget.** `estimated_tokens = len(prompt) / 3.5`. If that exceeds
   `llm.context_tokens`, the step logs a warning naming `OLLAMA_CONTEXT_LENGTH` and **still
   sends** the request. The estimate is recorded in the output.
5. **Call.** `llm_service.generate(TextRequest(prompt=..., prompt_version=...,
   temperature=cfg.temperature, max_tokens=cfg.max_tokens, timeout_s=cfg.request_timeout_s,
   metadata={"consumer": "lyrics_sourcing"}), StructureLabels)`. `LLMValidationError` or
   `LLMProviderError` propagates as `StepError("llm", ...)`.
6. **Validate** (`validate.py`, pure). `validate(labels, duration) -> tuple[StructureLabels, list[str]]`:
   - Clamps every `start`/`end` into `[0, floor(duration)]`.
   - Sorts sections by `start`.
   - Returns a list of *issues* (`end <= start`, overlaps, gaps over 2 s, a hook outside every
     `chorus_or_hook` section, clamped values).
   - Issues are **reported, never auto-fixed** beyond the clamp and sort. The experiment is partly
     about how well-formed a local model's output is.

The step writes `06_llm.json` (`StructureResult`), and `pipeline.py` then writes `summary.md` via
`summary.py`, because the summary needs the cues and lyrics from earlier steps. The summary is a
human-readable section table, the LLM hook next to `cue_derivation`'s `hook_in`/`hook_exit`
positions, the lyric lines that occur more than once (normalized text, with their start times),
the validation issues, the model id, and the token estimate.

**Prompt-level caching** comes from `llm_service`'s own cache in `llm.cache_dir`. Changing the
model, prompt version or timeline text naturally misses the cache.

### 4.8 Pipeline and resume (`pipeline.py`, `persistence.py`)

```
STEPS = ["ingest", "lyrics", "transcribe", "time_match", "metadata", "timeline", "llm"]
```

`run(url, cfg, from_step=None, refetch=False) -> RunSummary`:
1. Build every step's implementation via its factory **before** running anything, so a bad
   `impl` name fails in under a second rather than after a download.
2. `video_id = extract_video_id(url)` (production helper), and
   `out_dir = cfg.outputs_dir / video_id`.
3. For each step in order: if `from_step` is set and the step comes before it,
   `load_step(out_dir, step, Type)` reloads it. A missing file is an error naming the step to
   rerun from. Otherwise the step runs and its output is saved with `save_step` as
   `NN_<step>.json`:
   `01_ingest`, `02_lyrics`, `03a_transcribe`, `03_time_match`, `04_metadata`, `05_timeline`,
   `06_llm`.
4. A step's exception becomes `StepError(step, message)`. The run stops, and every earlier file
   stays on disk. The CLI prints the step name and message and exits 1.
5. It writes `run.json` holding a `RunSummary`, which also copies the config used.

`persistence.py`: `save_step` writes JSON via `to_jsonable` (dataclasses field by field,
pydantic via `.model_dump()`). `load_step` rebuilds through `from_dict`, a generic walker over
dataclass type hints. It rebuilds every contract, including the production `RawFeatures` and
`CueDerivationResult`, without copying `feature_extractor.cache._read`'s hand-written
reconstruction. (It isn't named `io.py`: running the CLI script puts its folder on `sys.path`,
where that name would shadow the standard library.)

## 5. Data contracts (`schema.py`)

All times are float seconds (design-v3 D20) unless noted. Everything is a dataclass except the
LLM output, which is pydantic because `llm_service` requires it.

```
IngestedTrack:
  video_id     : str
  url          : str
  path         : str               # audio file path, relative to repo root
  content_hash : str               # hash_file(path)
  duration     : float             # from yt-dlp
  raw_title    : str               # the video title
  title        : str | None        # yt-dlp `track`
  artist       : str | None        # yt-dlp `artist` / `creator`, first entry
  album        : str | None

LyricLine:
  start : float                    # relative to the lyrics' own recording
  end   : float | None             # next line's start; None for the last line
  text  : str

LyricsCandidate:
  source             : str         # fetcher name, e.g. "ytmusic" | "lrclib"
  source_ref         : str | None  # ytmusic browseId / lrclib record id
  status             : "synced" | "plain_only" | "not_found" | "error"
  lines              : list[LyricLine]   # non-empty iff status == "synced"
  plain_text         : str | None
  reference_duration : float | None      # duration of the recording the lyrics were timed to
  error              : str | None
  fetched_at         : str               # ISO-8601 UTC

LyricsFetchResult:
  candidates : list[LyricsCandidate]     # in lyrics.impl order

Word:        text: str, start: float, end: float, probability: float | None
Segment:     text: str, start: float, end: float, words: list[Word]
Transcript:
  language          : str | None
  segments          : list[Segment]      # time-ordered
  whisper_config_id : str
  model             : str

Alignment:                               # one per synced candidate
  source                 : str
  verdict                : "matched" | "offset_corrected" | "rejected" | "unverifiable"
  offset_s               : float | None
  anchorable_lines       : int
  inlier_lines           : int
  line_coverage          : float | None
  median_abs_residual_s  : float | None
  drift_slope            : float | None
  transcript_density_wpm : float
  urdu_script_words      : int

LyricSegment:                            # same shape as 04_transcription.md §3.3's draft
  start      : float
  end        : float
  text       : str
  confidence : float | None

SyncedLyrics:
  source           : str                 # winning fetcher name, or "whisper"
  verdict          : "matched" | "offset_corrected" | "unverifiable" | "fallback"
  offset_applied_s : float
  segments         : list[LyricSegment]
  lines_dropped    : int
  alignments       : list[Alignment]
  thresholds       : dict[str, float]    # the time_match config in force

TrackMetadata:
  raw  : RawFeatures                     # ingestion.feature_extractor.schema
  cues : CueDerivationResult             # ingestion.cue_derivation.schema

TimelineHeader:   the §4.6 header fields, in that order; all nullable except video_id, duration
TimelineRow:      the §4.6 columns, in that order; all nullable except t
Timeline:
  header : TimelineHeader
  rows   : list[TimelineRow]
  lyrics : list[LyricSegment]

# pydantic (LLM output schema; Field(description=...) on every field, which the model sees)
SectionType = Literal["intro", "verse", "pre_chorus", "chorus_or_hook", "bridge",
                      "interlude", "instrumental", "outro"]
LabeledSection(BaseModel): type: SectionType, start: int, end: int,
                           confidence: float (0..1), evidence: str
HookWindow(BaseModel):     start: int, end: int, reason: str
StructureLabels(BaseModel): sections: list[LabeledSection], hook: HookWindow, notes: str

StructureResult:
  labels           : StructureLabels     # after validate() clamp/sort
  issues           : list[str]
  model            : str
  prompt_version   : str
  estimated_tokens : int
  serializer       : str                 # "toon" | "json"

RunSummary:
  video_id       : str
  steps_run      : list[str]
  steps_reloaded : list[str]
  config         : dict                  # ExperimentConfig.model_dump()
  started_at     : str
  finished_at    : str

StepError(Exception): step: str, message: str
```

## 6. CLI

```
uv run --group experiments python src/experiments/lyrics_sourcing/run_experiment.py \
    <youtube-url> [<youtube-url> ...] \
    [--config path/to/config.yaml] [--from-step <step>] [--refetch]
```

- Several URLs run sequentially. One track's `StepError` is printed and the next track still
  runs. The exit code is 1 if any track failed.
- `--from-step llm` after changing `llm.model` reruns only step 6. `--from-step timeline` after
  switching `timeline.serializer` reruns steps 5–6.
- The script inserts `src/` into `sys.path`, the same as `llm_camelot_sequencer/run_experiment.py`.

## 7. Outputs

`outputs/<video_id>/`:

| File | Contents |
|---|---|
| `01_ingest.json` … `06_llm.json` | Each step's output (§4.8), and the resume point. |
| `timeline.toon` / `timeline.json` | Exactly what the LLM was sent. |
| `clicks.wav`, `clicks_raw.wav` | By-ear timing check (§4.4.5). |
| `summary.md` | Human-readable result (§4.7). |
| `run.json` | `RunSummary`, including the config used. |

Conclusions go into `04`/`05` by hand. This experiment never edits specs.

## 8. Testing

Pure modules are unit-tested with synthetic data. Network, Whisper, Ollama, downloading and
feature extraction are not, following the `whisper_bakeoff`/`llm_camelot_sequencer` precedent.
The parsing halves of the network code are pure functions tested on recorded fixture payloads.

| Test | Covers |
|---|---|
| `test_config.py` | The committed `config.yaml` loads; an unknown key fails; `lyrics.impl` accepts a list. |
| `test_persistence.py` | `save_step`/`load_step` round-trip for every contract, including `TrackMetadata`. |
| `steps/test_factories.py` | Every registry name builds (constructors do no I/O); an unknown `impl` raises with the valid names; changing `impl` returns the other class. |
| `lyrics/test_lrc.py` | Multi-timestamp lines, `[offset:]` sign, metadata tags, empty lines, `end` chaining. |
| `lyrics/test_ytmusic_parse.py`, `test_lrclib_parse.py` | Timed/plain/missing payloads map to the right status and lines; `clean_title`. |
| `time_match/test_normalize.py` | Devanagari → Roman, punctuation, Urdu passthrough and count. |
| `time_match/test_align.py` | Zero offset → `matched`; a +7.3 s shift → `offset_corrected` with `d0 ≈ 7.3`; a repeated chorus doesn't mislead the vote; sparse transcript → `unverifiable`; the wrong song's lyrics → `rejected`. |
| `time_match/test_resolve.py` | Coverage tie-break by priority; unverifiable beats Whisper; all rejected → Whisper; shift, clamp and `lines_dropped`; line-end rules. |
| `timeline/test_per_second.py` | Bar mapping at `t+0.5`; nulls outside the grid; min-max scaling, including a constant series; cue/phrase/riser/lyric placement; row count `floor(duration)+1`. |
| `timeline/test_toon.py` | Golden-string header plus tables; every quoting rule; null and number formatting. |
| `llm/test_validate.py` | Clamp, sort, and each issue type; nothing auto-fixed beyond clamp/sort. |
| `llm/test_prompt.py` | The template renders with a sample timeline; the version is parsed; no unfilled `{placeholders}`. |

## 9. Open questions

- **Q1 — `ytmusicapi` timed lyrics on this catalogue.** The API exists, and upstream recently
  fixed crashes on lines without `cueRange`. Whether it works unauthenticated for Bollywood
  tracks is checked on the first run. If it doesn't, LRCLIB carries the chain and this is
  recorded.
- **Q2 — Local model choice.** `qwen3:14b` is a default, not a finding. It is a reasoning model,
  and if its thinking output interferes with forced tool calls, try `qwen2.5:14b-instruct` (a
  config change). Hindi/Urdu comprehension of the lyrics is part of what the run shows.
- **Q3 — Non-constant offsets.** A video edit can insert material mid-song. v1 detects this only
  indirectly (low coverage leads to `rejected`), and piecewise offsets are a later amendment.
- **Q4 — Timeline resolution and size.** One row per second is about 240 rows for 4 minutes.
  Whether that fits comfortably in a 16k context, or whether per-bar rows (fewer, and aligned to
  musical structure) work better for the LLM, is a direct follow-up: a new `timeline` impl
  (`per_bar`), not a rewrite.
- **Q5 — Labels vs. boundaries.** `05` §1 argues that a model shouldn't invent boundaries, and
  that deterministic segmentation should find them first. Here the model picks boundaries from
  the rows' `t` values, which is a lookup, not a free invention, but still a judgment. `issues`
  and the comparison with `phrase_grid` in `summary.md` show how much that matters.
- **Q6 — Coverage study (future).** Running this pipeline over 15–20 tracks with a by-ear audit
  and a go/no-go rule for amending `04` to fetch-first is the natural next experiment, and needs
  no new step code.
- **Q7 — Production cache key and terms of use.** Fetched lyrics aren't a function of
  `content_hash`, and `ytmusicapi` is unofficial. Both are decisions for `04` if this goes
  anywhere.

## 10. Rejected alternatives

| Alternative | Why not |
|---|---|
| Auto-generated YouTube captions | They're YouTube's own ASR, usually disabled or `[Music]` on music, so no better than local Whisper and with less control. |
| Trust fetched timings without validation | The album-vs-video timing mismatch is the specific failure step 3 exists to catch. `passthrough` is kept only as a baseline impl. |
| Gate LRCLIB results on duration | Music-video edits differ in length from album cuts, so a duration gate throws away lyrics a constant offset would fix. |
| A TOON library dependency | Immature packages (a name reservation, a git-only beta) for a few dozen lines of encoding we fully control. |
| `langchain-ollama` / a new `common/llm_service` provider | Ollama's `/v1` is OpenAI-compatible, so the existing `OpenAICompatibleLLMService` works. External registration keeps `common/` untouched. |
| `load_config` with a `.env` key for Ollama | It requires a real env-var API key. Building `LLMServiceConfig` directly from the experiment's `config.yaml` keeps the folder self-contained. |
| Plugin auto-discovery for step implementations | Explicit registry dicts are easier to read and debug, and adding one line per impl is no burden. |
| One module per stage without interfaces (the `llm_camelot_sequencer` style) | The user's explicit goal is swapping implementations per step. |
| Stop fetching after the first source succeeds | Hides per-source results and removes the chance to prefer a better-aligned candidate. Fetching is cheap. |
| Best-single-match anchoring per line | Chorus lines repeat, so the vote uses multiple candidates per line. |
| Extending `DownloadedTrack` with `track`/`artist`/`album` | Changes a production contract for an experiment. One extra metadata probe per track is cheaper. |

## Amendments

- 2026-09-30 — Whisper default set to `small` (§3.2, §4.3), with a planned turbo comparison.
  All model weights live in the repo-root `models/` dir: Whisper via `transcribe.models_dir`,
  Ollama via `OLLAMA_MODELS` on the server (§2).
- 2026-09-30 — Changes made while implementing. None changes a contract's fields.
  - `io.py` is renamed `persistence.py`, with a generic `from_dict` (§4.8).
  - Added `summary.py` (§4.7) and `tests/.../builders.py`.
  - The offset vote uses a sliding window rather than fixed histogram bins (§4.4.3).
  - The click track is written by the pipeline rather than inside `offset_vote` (§4.4).
  - `StructureLabeler.label` takes the serializer name (§4.7).
  - LRCLIB `/api/get` only runs when title, artist and album are all known; `/api/search`
    uses `track_name`/`artist_name` when both are known (§4.2).
  - `__init__.py` files are placed through the test tree, because `test_config.py` collides
    with an existing test file (§3.3).
