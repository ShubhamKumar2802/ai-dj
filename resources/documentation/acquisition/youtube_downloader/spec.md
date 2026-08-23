# YouTube Downloader — Spec

**Layer:** `acquisition/` — new layer, upstream of `ingestion/`. External I/O
(network + a system `ffmpeg` dependency), not audio analysis; produces the local
file paths `ingestion/orchestrator` already expects as input, rather than sitting
inside that layer.

---

## 0. Invariant

> This module's only job is: given a YouTube URL, produce a local MP3 file and a
> small amount of source metadata. It does no audio analysis, no cue derivation,
> no DSP of any kind — its output (`DownloadedTrack.path`) is exactly the kind of
> local file path `ingestion.orchestrator.ingest_tracks` already accepts
> (orchestrator spec §1: `ingest_tracks(paths: list[str], ...)`). This module is a
> *producer* of that input, not a consumer of anything downstream.

---

## 1. Scope & consumers

**Boundary:** `download_tracks(urls: list[str], config: DownloadConfig, on_progress:
OnProgress | None = None) -> DownloadResult` takes a list of YouTube URLs and
returns local MP3 paths plus failures. Its output feeds
`ingestion.orchestrator.ingest_tracks(paths=[t.path for t in result.tracks], ...)`
directly — this module never calls into `ingestion/` itself; wiring the two
together is the caller's job (a future top-level pipeline entry point, not yet
specced).

**v1 scope, stated explicitly:**
- One URL = one video = one output file. Playlist URLs are not expanded
  (`noplaylist: True`, §5) — a playlist URL downloads at most the single target
  video, never silently fans out into N files.
- No search-by-title (rejected in scoping, §10) — every input is a URL the caller
  already resolved.
- **Idempotent across runs, by video id.** A `video_id` already recorded in the
  manifest (§6) is never re-downloaded — the existing file is returned instead.
  This is real application-level de-dup, not incidental tool behavior (contrast
  the note in §7 about yt-dlp's own unrelated on-disk skip).
- Personal-use tool: for downloading audio the caller has the rights to use in a
  personal mix. No bulk/mass-download safeguards, no DRM circumvention, no
  re-distribution features — out of scope by design, not an oversight.

**Explicitly out of scope:**
- `ingestion/orchestrator` and everything downstream — this module's output is
  exactly their input; nothing about how they consume `DownloadedTrack`/paths is
  this spec's concern.
- Search-by-title/artist matching — deliberately deferred (§10, §11 Q1).
- Any wiring/CLI that chains `download_tracks` → `ingest_tracks` into one
  command — a future top-level script, not this module (§11 Q2).
- **Propagating download provenance (source URL, `downloaded_at`, `run_id`)
  into `ingestion.orchestrator.Track`.** Considered and explicitly rejected
  (§10) — `Track` stays exactly as that already-implemented module's spec
  defines it, untouched. The manifest (§6), keyed by `video_id` and
  inspectable by `path`, is the sole provenance source; nothing propagates
  further downstream. Doing otherwise would mean amending an already-approved,
  already-built module's spec (and its code) — real scope beyond this module.

---

## 2. Data contract (`schema.py`, `config.py`, `interface.py`)

```
DownloadedTrack:
  url            : str            # the input URL, unchanged
  path             : str            # local filesystem path to the downloaded mp3
  video_id           : str            # source video id — embedded in the
                                        # filename (§5) for traceability
  title                 : str            # source title
  uploader                : str | None    # source uploader/channel — None if
                                            # unavailable
  duration                   : float        # seconds

DownloadFailure:
  url         : str
  error         : str   # str(exception) — plain, picklable; mirrors
                          # ingestion.orchestrator.IngestionFailure (orchestrator
                          # spec §2) for consistency across the codebase
  error_type      : str   # type(exception).__name__

DownloadResult:
  tracks[]      : list[DownloadedTrack]
  failures[]      : list[DownloadFailure]
  run_id          : str   # uuid4, one per download_tracks() call — bundles every
                            # track/failure in this result as belonging to the
                            # same run (§4). Lives on the result, not on each
                            # DownloadedTrack/DownloadFailure individually — every
                            # track in a result already shares one run_id by
                            # construction, so a per-track copy would be pure
                            # duplication (§11 Q6 revisits this if a future
                            # consumer ever needs a track separated from its
                            # batch to still know its run)

DownloadConfig:
  output_dir         : str = "music"   # matches the repo's existing gitignored
                                          # music/ convention (.gitignore: "#
                                          # testing tracks" / "/music"; also
                                          # feature_extractor's and orchestrator's
                                          # real-audio smoke-test fixture dir)
  audio_format          : str = "mp3"
  audio_quality            : str = "0"    # ffmpeg VBR quality scale passed to
                                            # yt-dlp's FFmpegExtractAudio
                                            # postprocessor; "0" = best
  filename_template           : str = "%(title)s [%(id)s].%(ext)s"   # yt-dlp
                                          # output template; video id embedded so
                                          # same-titled videos never collide
  embed_metadata                  : bool = True   # runs yt-dlp's FFmpegMetadata
                                                     # postprocessor (title/uploader
                                                     # as ID3 tags) — cosmetic, no
                                                     # downstream pipeline code
                                                     # reads ID3 tags
  retries                            : int = 3    # passed through to yt-dlp's own
                                                     # `retries` option (used in the
                                                     # options dict built in §5) —
                                                     # transient network retry is
                                                     # yt-dlp's job, not hand-rolled
                                                     # here
  manifest_dir                          : str = ".cache/youtube_downloader"   #
                                                     # idempotency manifest
                                                     # location (§6) — under
                                                     # .cache/, matching the
                                                     # repo's existing gitignored
                                                     # runtime-cache convention
                                                     # (.gitignore: ".cache/")

DownloadInfo:   # interface.py — the Downloader Protocol's own return type;
                # deliberately in this module's vocabulary, not a raw yt-dlp
                # info dict, so worker.py never needs to know any
                # implementation's internal result shape (§5)
  path        : str
  video_id       : str
  title             : str
  uploader             : str | None
  duration                : float

Downloader (Protocol):   # interface.py
  def run(self, url: str, config: DownloadConfig) -> DownloadInfo: ...

ManifestEntry:   # manifest.py — one persisted per video_id (§6)
  video_id           : str
  path                  : str
  title                    : str
  uploader                    : str | None
  duration                       : float
  first_run_id                      : str   # run_id of the run that FIRST
                                              # produced this entry — never
                                              # overwritten by a later hit
  downloaded_at                        : str   # ISO 8601 UTC timestamp
```

`DownloadedTrack`/`DownloadFailure`/`DownloadResult`/`DownloadConfig` naming
shape mirrors `ingestion.orchestrator`'s `Track`/`IngestionFailure`/
`IngestionResult`/`IngestionConfig` deliberately (orchestrator spec §2) — same
pattern, new domain. `Downloader`/`DownloadInfo` is this module's own addition,
not mirrored from orchestrator — see §5.

---

## 3. Per-URL worker (`worker.py`)

```
_default_downloader: Downloader = YtDlpDownloader()   # module-level singleton —
                                                        # YtDlpDownloader itself
                                                        # is stateless (§5), so one
                                                        # instance serves every call

_download_one(
    url: str,
    config: DownloadConfig,
    run_id: str,
    _downloader: Downloader = _default_downloader,
) -> DownloadedTrack | DownloadFailure
  video_id = extract_video_id(url)          # None if the URL shape isn't
                                              # recognized (§6) — not an error
  if video_id is not None:
      cached = read_manifest_entry(video_id, config)   # None on miss, or if
                                                          # the entry's file no
                                                          # longer exists (§6,
                                                          # self-healing)
      if cached is not None:
          return DownloadedTrack(
              url=url, path=cached.path, video_id=cached.video_id,
              title=cached.title, uploader=cached.uploader,
              duration=cached.duration,
          )
  try:
      info = _downloader.run(url, config)   # DownloadInfo, not a raw yt-dlp dict
      write_manifest_entry(
          ManifestEntry(video_id=info.video_id, path=info.path, title=info.title,
                         uploader=info.uploader, duration=info.duration,
                         first_run_id=run_id, downloaded_at=_utcnow_iso()),
          config,
      )
      return DownloadedTrack(
          url=url,
          path=info.path,
          video_id=info.video_id,
          title=info.title,
          uploader=info.uploader,
          duration=info.duration,
      )
  except Exception as exc:
      return DownloadFailure(url=url, error=str(exc), error_type=type(exc).__name__)
```

`_downloader` is an underscore-prefixed test-seam parameter — same pattern
`ingestion.orchestrator` already established for `_worker`/`_backend`
(orchestrator spec §5): tests inject a fake `Downloader` satisfying the
`Protocol` instead of monkeypatching module internals or hitting real yt-dlp/
network. `_download_one` itself never imports `yt_dlp` — only
`downloader_ytdlp.py` does (§5). `run_id` is a required (not test-seam) parameter
— every call needs to know which run it belongs to for manifest provenance (§6).

`read_manifest_entry` is called *outside* the `try`/`except` on purpose — it's
defensive by contract and never raises (§6), so it needs no guarding. Only
`write_manifest_entry` sits inside the `try`, meaning its own failure is caught
by the same broad `except` as a download failure (§7 states this trade-off
explicitly).

Catches `Exception` broadly and deliberately, same rationale as
`ingestion.orchestrator._ingest_one` (orchestrator spec §4): a geo-blocked,
age-restricted, private, deleted, or live-stream video, or a plain network
failure, must fail *that one URL* without aborting the batch. This broad catch
is agnostic to *which* `Downloader` is plugged in — it doesn't need to know
`yt_dlp.utils.DownloadError` or any other implementation's exception hierarchy
to stay correct; that's the point of catching at the `Downloader.run()`
boundary rather than inside `YtDlpDownloader` itself.

---

## 4. Dispatch (`download.py`)

```
ProgressStatus = "started" | "completed" | "failed"
OnProgress = Callable[[str, ProgressStatus], None]

download_tracks(
    urls: list[str],
    config: DownloadConfig,
    on_progress: OnProgress | None = None,
    _run_id: str | None = None,   # test seam — overrides the auto-generated
                                    # uuid4 so tests can assert on a known
                                    # value instead of a random one
) -> DownloadResult
```

Generates `run_id = _run_id or str(uuid4())` once, at the start of the call,
before dispatching any URL — every `DownloadedTrack`/`DownloadFailure` produced
during this call is a product of that one `run_id`, and it's threaded through to
`_download_one` (§3) for manifest provenance, and returned on `DownloadResult.run_id`
(§2).

**Sequential, not concurrent** — v1 scoping decision (§10): downloads are
network-bound against a single upstream (YouTube), and parallel connections raise
real throttling/blocking risk that a metadata-only or local-disk module (like
`orchestrator`) doesn't face. `ingestion/orchestrator`'s `joblib`/`loky`
concurrency (orchestrator spec §5) solves a different problem — CPU-bound DSP
crash-isolation — that doesn't apply here.

For each URL, in input order: `on_progress(url, "started")` fires immediately
before the download begins (not `"queued"` — sequential dispatch means there's no
meaningful gap between submission and start, unlike orchestrator's concurrent
dispatch where `"queued"` vs. `"started"` are genuinely different moments), then
`_download_one` runs to completion, then `on_progress(url, "completed" |
"failed")` fires based on the result type. `tracks[]`/`failures[]` are appended in
input order — sequential execution makes this free, unlike orchestrator's
`generator_unordered` tradeoff.

If `on_progress` itself raises, that exception propagates out of
`download_tracks` — same as orchestrator (spec §5 point 5): this module does not
swallow bugs in caller-supplied callbacks.

**No separate literal-URL dedup step is needed** (contrast orchestrator's
explicit path-level dedup, spec §5 point 1) — the manifest (§6) already covers
it for free: dispatch is sequential and `_download_one` writes its manifest
entry synchronously before returning, so if the same URL (or two different URLs
for the same video) appears twice in one `urls` list, the second occurrence
manifest-hits off the first's just-written entry instead of downloading again.

---

## 5. Downloader boundary (`interface.py`, `downloader_ytdlp.py`)

`interface.py` defines the `Downloader` `Protocol` and `DownloadInfo` (§2) — the
entire surface `worker.py` depends on. It imports nothing from `yt_dlp`.

`downloader_ytdlp.py` is the only concrete implementation in v1:

```
class YtDlpDownloader:   # satisfies the Downloader Protocol structurally —
                          # no explicit inheritance needed
  def run(self, url: str, config: DownloadConfig) -> DownloadInfo:
      ...
```

Stateless class (no `__init__` state) — safe as the module-level singleton §3
uses. Internally, `run()`:

1. Constructs a fresh `yt_dlp.YoutubeDL` instance *per call* (options depend on
   the per-call `config` argument, so this can't be pooled across calls with
   different configs; v1 keeps this simple, revisit only if construction
   overhead is ever measured as a real cost) with options:

   ```python
   {
       "format": "bestaudio/best",
       "outtmpl": os.path.join(config.output_dir, config.filename_template),
       "noplaylist": True,
       "retries": config.retries,
       "postprocessors": [
           {
               "key": "FFmpegExtractAudio",
               "preferredcodec": config.audio_format,
               "preferredquality": config.audio_quality,
           },
           *([{"key": "FFmpegMetadata"}] if config.embed_metadata else []),
       ],
   }
   ```

2. Calls `.extract_info(url, download=True)`, getting yt-dlp's own info dict.
3. Resolves the final `.mp3` path from that dict (yt-dlp's `prepare_filename`
   plus the postprocessor's extension swap — the mechanism yt-dlp itself
   recommends, since `outtmpl`'s rendered path before extraction still carries
   the *pre-conversion* extension) and maps the dict's `id`/`title`/`uploader`/
   `duration` fields into a `DownloadInfo`.

All yt-dlp-specific knowledge — info-dict key names, the extension-swap
mechanics, postprocessor config shape — lives in this one file. A future second
`Downloader` implementation only needs to produce a `DownloadInfo`; nothing
else in this module changes (§10).

---

## 6. Idempotency & the download manifest (`video_id.py`, `manifest.py`)

**Why this exists:** confirmed with the user that "idempotency across runs"
means real dedup, not just a traceability tag — a `video_id` already downloaded
in *any* prior `download_tracks()` call must be recognized and skipped, not
just within one call.

**The manifest is one persistent, continuously-accumulating store under
`config.manifest_dir` — not scoped per run.** Every `download_tracks()` call
reads whatever has accumulated there from *every* prior run and writes new
entries into that same store; nothing about it is reset or partitioned per
`run_id`. A fresh manifest per run would make cross-run idempotency
impossible by definition — `run_id` only tags *provenance* (`first_run_id`,
below), it never partitions storage.

```
extract_video_id(url: str) -> str | None
```

Pure, local, no network call — parses the common YouTube URL shapes
(`youtube.com/watch?v=ID`, `youtu.be/ID`, `youtube.com/shorts/ID`,
`youtube.com/embed/ID`, each tolerant of extra query params/trailing slash) and
returns the video id, or `None` for anything it doesn't recognize. Deliberately
**not** implemented by calling yt-dlp's own `extract_info(url, download=False)`
to resolve the id — that would still cost a network round-trip on *every* check,
defeating the point of a cheap pre-download idempotency check (§10). `None` is a
normal, non-error outcome: a URL this function can't parse simply gets no
idempotency and always re-downloads (fail-open, never fail-wrong — §7).

```
read_manifest_entry(video_id: str, config: DownloadConfig) -> ManifestEntry | None
  # loads {config.manifest_dir}/{video_id}.json if present.
  # Self-healing, and — deliberately — never raises: missing file, malformed/
  # truncated JSON (e.g. a manifest write that was interrupted before v1's
  # atomic rename could apply — see the temp-file discussion below), a JSON
  # object missing an expected key, AND a `.path` that no longer exists on
  # disk (the user deleted the file, moved output_dir, etc.) all collapse to
  # the same outcome: return None, i.e. "treat as a miss." This is why §3's
  # `_download_one` calls this *outside* its own try/except — a corrupted or
  # unreadable manifest entry must never be able to crash the whole batch
  # (the module's own §3 invariant), and treating any unusable entry as a
  # plain miss is simpler than a second failure path for "the cache itself is
  # broken." A fresh download's `write_manifest_entry` (below) naturally
  # repairs a corrupted entry on the next successful run for that video_id.

write_manifest_entry(entry: ManifestEntry, config: DownloadConfig) -> None
  # Atomic temp-file + rename into {config.manifest_dir}/{video_id}.json — the
  # same Fix 1 pattern feature_extractor's cache.py already established
  # (feature_extractor spec §5): write to a uniquely-named temp file, then
  # os.replace() onto the final path. No cross-process lock/claim (that spec's
  # Fix 2) — within one download_tracks() call, dispatch is sequential (§4) so
  # there's no concurrent writer to coordinate with. Two *separate* processes
  # each running their own download_tracks() call are a different story — see
  # §7's stated limitation; atomic writes alone keep that race non-corrupting,
  # just not duplicate-work-free.
```

`_download_one` (§3) checks the manifest *before* calling the `Downloader`, and
writes to it immediately after a successful download, keyed on the freshly
downloaded `DownloadInfo.video_id` (not the pre-download `extract_video_id`
guess, in case they ever diverge — the post-download id from the actual
extraction is authoritative). A hit short-circuits entirely: no `Downloader.run()`
call, no network, no ffmpeg invocation — just building a `DownloadedTrack` from
the stored entry.

`ManifestEntry.first_run_id` (§2) is write-once — a cache hit never updates it,
so it always answers "which run first brought this track in," while
`DownloadResult.run_id` (§2, §4) always reflects the *current* call regardless
of whether a given track was a fresh download or a manifest hit.

---

## 7. Known v1 limitations

**Requires `ffmpeg` on `PATH` — an external system binary, not a pip
dependency.** `FFmpegExtractAudio` shells out to it; if it's missing, yt-dlp
raises a `PostProcessingError` naming ffmpeg, which surfaces as an ordinary
`DownloadFailure` (§3) for every URL, not a clear upfront error. **Not fixed in
v1** — no startup check for ffmpeg's presence is added; stated here rather than
silently discovered later, per this repo's "honest about weakness" convention
(e.g. `feature_extractor`'s `downbeat_confidence`, orchestrator spec §6). Note
this only bites on a manifest *miss* — a manifest hit (§6) never reaches
`YtDlpDownloader` at all.

**The manifest key is `video_id` only — not versioned by `DownloadConfig`.**
Unlike `feature_extractor`'s cache key, which is `(content_hash,
extractor_version)` specifically so a changed extraction algorithm invalidates
stale entries, this manifest has no equivalent version component. If a track was
downloaded once as mp3 and a later run changes `DownloadConfig.audio_format` or
`.audio_quality`, the manifest still returns the *original* file under the old
settings — the new settings are silently ignored for any already-downloaded
video. **Not fixed in v1** — flagged rather than solved; see §11 Q4.

**`extract_video_id`'s URL-shape coverage is incomplete by construction (§6).**
Any YouTube URL shape it doesn't recognize (e.g. `music.youtube.com`, or an
unusual parameter ordering) silently gets no idempotency, not an error — every
call for that URL re-downloads. Deliberate fail-open choice: never wrong, just
sometimes not deduped. See §11 Q5.

**"Already downloaded" is *also*, separately, yt-dlp's own default behavior.**
Independent of this module's manifest, if `outtmpl` resolves to a path that
already exists, yt-dlp itself skips re-downloading it. This only matters on a
manifest miss that still happens to land on an existing path (e.g. a manifest
entry got deleted but the file didn't) — incidental tool behavior, not something
this module relies on for correctness (§6 owns idempotency).

**A `write_manifest_entry` failure after a successful download is reported as a
`DownloadFailure`, even though the file exists and is valid.** §3's broad
`try`/`except` wraps the download *and* the manifest write as one unit — if the
write fails (e.g. `manifest_dir` unwritable, disk full) after `Downloader.run()`
already succeeded, the caught exception produces a `DownloadFailure` for a URL
whose audio file is actually sitting on disk, just not recorded in the manifest
(so a later run won't recognize it and will redownload — self-healing, per §6,
just not on this attempt). **Not fixed in v1** — an honest trade-off of one
simple `try`/`except` covering the whole operation, not a design that tries to
distinguish "download failed" from "download succeeded but bookkeeping failed."

**No cross-process lock on manifest writes (§6, §10) means two separate OS
processes** — not just concurrent calls within one process, which can't happen
given §4's sequential dispatch — **calling `download_tracks()` at the same time
against the same `manifest_dir` can both cache-miss the same `video_id` and both
redundantly download+transcode it.** Atomic temp+rename (§6) still guarantees
the manifest *file* itself is never corrupted by the race — one write wins,
cleanly — so this costs duplicate work, never a corrupted cache. `orchestrator`
faces the equivalent problem from concurrent *workers within one call*
(`joblib`/`loky`, its own spec §5) and solves it with a full lock/claim
protocol; this module's rejection of that protocol (§10) is scoped specifically
to *that* problem, which its sequential design eliminates — it does not claim
anything about two independent processes racing, which is a real (if narrow)
gap, left open rather than solved in v1.

**YouTube's extraction internals change without notice**, and yt-dlp releases
frequently to track those changes — a pinned old version of `yt-dlp` can start
failing on *every* URL with no code change on this repo's side. Not solved here
beyond a normal dependency-version bump when it happens; noted as an operational
reality, not a design flaw.

---

## 8. Testing strategy

- **`test_video_id.py`** — `extract_video_id()` against a fixture table of
  recognized URL shapes (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, with
  extra query params/trailing slashes) plus unrecognized shapes asserting `None`
  — pure function, no I/O.
- **`test_manifest.py`** — `read_manifest_entry`/`write_manifest_entry` against
  a `tmp_path`-based `DownloadConfig.manifest_dir`: round-trip read-after-write,
  the atomic temp+rename behavior, and every `read_manifest_entry` self-healing
  case returning `None` rather than raising — missing file, malformed/truncated
  JSON, a JSON object missing an expected key, and a `.path` that doesn't exist
  on disk (§6).
- **`test_worker.py`** — `_download_one`'s manifest-hit short-circuit (no
  `Downloader.run()` call at all on a hit), the manifest-miss → download →
  `write_manifest_entry` path, a corrupted manifest entry degrading to a fresh
  download rather than propagating (§6), a `write_manifest_entry` failure after
  a successful `Downloader.run()` still surfacing as a `DownloadFailure` (§7),
  and the plain `try`/`except` → `DownloadFailure` conversion for a `Downloader`
  failure — via a small fake `Downloader` (satisfying the `Protocol`, §5)
  injected through the `_downloader` test-seam parameter (§3) and a `tmp_path`
  manifest dir. No real network, no real yt-dlp, no monkeypatching.
- **`test_downloader_ytdlp.py`** — `YtDlpDownloader.run()`'s own logic in
  isolation: the options dict built from a `DownloadConfig`, and the output-path/
  extension-swap resolution, against fixture yt-dlp info-dicts (with
  `yt_dlp.YoutubeDL` itself mocked at this layer only — this is the one file
  where yt-dlp's actual shape matters).
- **`test_download.py`** — dispatch order, partial-failure collection,
  progress-callback firing (`"started"`/`"completed"`/`"failed"`), `run_id`
  generation/propagation onto `DownloadResult` (via the `_run_id` test seam,
  §4), and the same-URL-twice-in-one-call dedup-for-free behavior (§4) — using a
  fake `_download_one` — no real network.
- **`test_real_download_smoke.py`** — skip-guarded on an explicit opt-in
  environment variable (`AI_DJ_RUN_LIVE_YOUTUBE_TESTS=1`), since unlike
  `orchestrator`'s `music/`-presence guard (a local fixture that either exists or
  doesn't), there's no local signal for "network + real YouTube is available and
  desired right now" — running live network calls by default would make the
  default suite flaky and slow. Downloads one short, stable, known-public test
  video end-to-end through the real `YtDlpDownloader` and asserts the output file
  exists and is a valid audio file, then calls `download_tracks` on the same URL
  a second time and asserts the manifest hit (no second network fetch).

---

## 9. File layout

```
src/acquisition/youtube_downloader/
  __init__.py             # public exports: DownloadedTrack, DownloadResult,
                           # DownloadFailure, DownloadConfig, download_tracks
  schema.py                # DownloadedTrack, DownloadResult, DownloadFailure (§2)
  config.py                 # DownloadConfig (§2)
  interface.py                # Downloader Protocol, DownloadInfo (§2, §5)
  downloader_ytdlp.py            # YtDlpDownloader — the only implementation (§5)
  video_id.py                       # extract_video_id() (§6)
  manifest.py                          # ManifestEntry, read/write_manifest_entry (§6)
  worker.py                               # _download_one(), _default_downloader (§3)
  download.py                                # download_tracks() dispatch loop (§4)
  examples/
    example_download.py              # manual smoke script, mirrors
                                      # orchestrator's example_ingest.py —
                                      # gitignored, not part of the test suite

tests/acquisition/youtube_downloader/
  conftest.py               # fixture DownloadInfo/ManifestEntry values + fake Downloader
  test_video_id.py             # §8
  test_manifest.py                # §8
  test_worker.py                    # §8
  test_downloader_ytdlp.py             # §8
  test_download.py                        # §8
  test_real_download_smoke.py                # §8
```

**New dependency: `yt-dlp`** (added at implementation time via `uv add yt-dlp`,
not part of drafting this spec). **New external (non-pip) dependency: `ffmpeg`
must be present on the system `PATH`** (§7) — documented in setup instructions at
implementation time, not installable via `uv`. Manifest I/O (`manifest.py`) uses
only stdlib (`json`, `os`, `uuid`, `datetime`) — no new dependency, mirroring
`feature_extractor`'s cache (spec §5: "No new dependency").

---

## 10. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Search-by-title/artist input (resolve a plain string to a YouTube result) | URLs only in v1 | Adds ranking/matching logic and a new silent-failure mode (wrong track picked) on top of an already-new module; caller already knows which URL they want for v1's scope |
| No idempotency at all — every call re-downloads everything | Persisted `video_id`-keyed manifest, real dedup across runs (§6) | Reopened during scoping specifically because the user wants repeated runs against overlapping track lists (the normal megamix-building workflow) not to re-hit YouTube/re-transcode every time |
| Parallel downloads (mirroring `orchestrator`'s `joblib`/`loky` pattern) | Sequential dispatch (§4) | Downloads are network-bound against one upstream host; concurrent connections raise real throttling/blocking risk that doesn't apply to `orchestrator`'s CPU-bound, crash-isolation problem |
| Placing this module under `ingestion/` (grouped with `feature_extractor`/`cue_derivation`/`orchestrator`) | New `acquisition/` layer | `ingestion/` in this codebase specifically means "audio in, expensive, cached per track" analysis (design-v3 stage 1); this module does no analysis at all — it's external I/O that produces the input `ingestion/orchestrator` already expects |
| Expanding playlist URLs into many tracks | `noplaylist: True` — a playlist URL yields at most one video (§1, §5) | Keeps the URL-in/file-out contract 1:1 and predictable; silent fan-out from one input to N outputs would break the caller's ability to reason about `len(urls)` vs. `len(result.tracks) + len(result.failures)` |
| Full `llm_service`-style `factory.py` + `providers/registry.py` (`register_downloader`/`get_downloader_factory`, lookup-by-name) | Thin `Downloader` `Protocol` (§2, §5) + one directly-imported `YtDlpDownloader`, no registry | `llm_service`'s registry earns its cost because multiple concrete LLM providers are a real, current need (orchestrator/llm_service specs already argue this). Here there is exactly one real implementation today and no second one on the table — a name-keyed registry would be built for a swap that isn't concretely happening yet |
| No interface at all — a bare `_run_ytdlp()` function called directly from `worker.py` | `Downloader` `Protocol` boundary (§2, §5), even with only one implementation | This specific domain has real, non-hypothetical precedent for library churn (`yt-dlp` is itself a fork born when `youtube-dl` went stale) — unlike most speculative interfaces, "we might need to swap this" is grounded in something that already happened once. A `Protocol` costs one small file and keeps the swap contained to `downloader_ytdlp.py` |
| `download_tracks` → `ingest_tracks` convenience wrapper (e.g. `acquire_and_ingest()`) | Two fully separate calls; caller wires them together (§1, §11 Q2) | Keeps `acquisition/` with zero dependency on `ingestion/` — not even a one-way import. Considered and explicitly rejected by the user during scoping |
| Resolving `video_id` via `yt_dlp.extract_info(url, download=False)` for the idempotency pre-check | Pure local URL parsing, `extract_video_id()` (§6) | A metadata-only yt-dlp call is still a real network round-trip; doing that on every check to decide whether to skip a *download* would keep most of the cost the check exists to avoid. Trade-off: only recognizes common URL shapes (§7) |
| Single shared `manifest.json` (all video_ids in one file) | One JSON file per `video_id`, under `manifest_dir` (§6) | Matches this repo's existing convention exactly (`llm_service`, `feature_extractor` both cache one-file-per-key); avoids read-modify-write contention on one ever-growing shared file |
| Cross-process lock/claim on manifest writes (mirroring `feature_extractor` cache's v3 Fix 2) | Atomic temp+rename only, no lock (§6) | That lock exists to coordinate *concurrent workers within one call* racing on the same key — exactly `orchestrator`'s situation (`joblib`/`loky` workers), which this module's sequential dispatch (§4) structurally can't produce. It does **not** cover two independent OS processes each running their own `download_tracks()` call against the same `manifest_dir` — that residual race is real and left open (§7), not solved by "sequential" |
| Adding `source_url`/`downloaded_at`/`run_id` as nullable fields on `ingestion.orchestrator.Track`, populated by `_assemble_track` when a track came from this module | `Track` stays untouched; the manifest (§6) is the sole provenance source, looked up by `path`/`video_id` if ever needed | `Track` belongs to `ingestion/orchestrator`, an already-approved *and already-implemented* spec (`overview.md`: Spec Done, Code Done). Adding fields there — even nullable ones that wouldn't break existing conformance — is a real Amendment to a second, already-built module (per `resources/documentation/README.md`'s amendment rule) plus matching `_assemble_track`/`ingest_tracks` code changes: genuinely larger scope than this new module's own spec, and explicitly declined |

---

## 11. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Should a future version support playlist expansion or search-by-title, and if so does that change `DownloadConfig`/`download_tracks`'s signature or add a new entry point? | Nothing in v1 — deferred scope, not blocking this spec |
| Q2 | Does the eventual top-level pipeline (chaining this module → `ingestion.orchestrator.ingest_tracks`) want a single combined entry point, or stay as two explicit calls the caller wires together? | Not this module's concern (§1) — relevant once a top-level CLI/script is specced |
| Q3 | Is `retries=3` (yt-dlp's own retry option, §2/§5) the right default, or does YouTube's real-world transient failure rate need something different? | Low blast radius — a config default, easy to change later with no contract impact |
| Q4 | Should the manifest key incorporate `DownloadConfig`'s format/quality settings (versioning it the way `feature_extractor`'s key includes `extractor_version`), so a settings change invalidates stale entries instead of silently returning them (§7)? | Correctness of idempotency under a changed `DownloadConfig` — currently a known, stated limitation, not yet a bug someone has hit |
| Q5 | Does `extract_video_id` need to cover `music.youtube.com` or other YouTube-family domains for v1's real usage, or is `youtube.com`/`youtu.be` sufficient (§7)? | Idempotency coverage breadth — low blast radius, fails open (just re-downloads) rather than incorrectly |
| Q6 | Should `DownloadedTrack`/`DownloadFailure` carry their own `run_id` (not just `DownloadResult`), for a future consumer that persists tracks independently of their batch (§2)? | Schema shape if that need materializes — no current consumer needs it |
