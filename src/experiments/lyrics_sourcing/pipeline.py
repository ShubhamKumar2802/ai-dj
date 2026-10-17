"""Wires the steps together; every step's output lands on disk before the next runs (spec §4.8).

`from_step` reloads everything before it from `outputs/<video_id>/`, so swapping one step's
implementation (e.g. a different LLM model) reruns only that step and what follows.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acquisition.youtube_downloader.video_id import extract_video_id
from experiments.lyrics_sourcing.config import ExperimentConfig
from experiments.lyrics_sourcing.persistence import load_step, save_step
from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    LyricsFetchResult,
    RunSummary,
    StepError,
    StructureResult,
    SyncedLyrics,
    Timeline,
    TrackMetadata,
    Transcript,
    utc_now,
)
from experiments.lyrics_sourcing.steps.ingest import factory as ingest_factory
from experiments.lyrics_sourcing.steps.ingest.interface import TrackIngester
from experiments.lyrics_sourcing.steps.llm import factory as llm_factory
from experiments.lyrics_sourcing.steps.llm.interface import StructureLabeler
from experiments.lyrics_sourcing.steps.lyrics import factory as lyrics_factory
from experiments.lyrics_sourcing.steps.lyrics.fetch_cache import fetch_all
from experiments.lyrics_sourcing.steps.lyrics.interface import LyricsFetcher
from experiments.lyrics_sourcing.steps.metadata import factory as metadata_factory
from experiments.lyrics_sourcing.steps.metadata.interface import MetadataExtractor
from experiments.lyrics_sourcing.steps.time_match import factory as time_match_factory
from experiments.lyrics_sourcing.steps.time_match.click_track import write_click_track
from experiments.lyrics_sourcing.steps.time_match.interface import TimeMatcher
from experiments.lyrics_sourcing.steps.timeline import factory as timeline_factory
from experiments.lyrics_sourcing.steps.timeline.interface import (
    TimelineBuilder,
    TimelineSerializer,
)
from experiments.lyrics_sourcing.steps.transcribe import factory as transcribe_factory
from experiments.lyrics_sourcing.steps.transcribe.interface import Transcriber
from experiments.lyrics_sourcing.summary import build_summary

STEPS = ("ingest", "lyrics", "transcribe", "time_match", "metadata", "timeline", "llm")

STEP_FILES = {
    "ingest": "01_ingest",
    "lyrics": "02_lyrics",
    "transcribe": "03a_transcribe",
    "time_match": "03_time_match",
    "metadata": "04_metadata",
    "timeline": "05_timeline",
    "llm": "06_llm",
}

STEP_TYPES: dict[str, type] = {
    "ingest": IngestedTrack,
    "lyrics": LyricsFetchResult,
    "transcribe": Transcript,
    "time_match": SyncedLyrics,
    "metadata": TrackMetadata,
    "timeline": Timeline,
    "llm": StructureResult,
}

OnStep = Callable[[str, str], None]  # (step, "running" | "reloaded" | "done")


@dataclass
class Steps:
    ingester: TrackIngester
    fetchers: list[LyricsFetcher]
    transcriber: Transcriber
    matcher: TimeMatcher
    extractor: MetadataExtractor
    builder: TimelineBuilder
    serializer: TimelineSerializer
    labeler: StructureLabeler


def build_steps(cfg: ExperimentConfig) -> Steps:
    """Every implementation is built before anything runs, so a bad `impl` name fails in
    under a second rather than after a download."""
    return Steps(
        ingester=ingest_factory.build(cfg.ingest),
        fetchers=lyrics_factory.build(cfg.lyrics),
        transcriber=transcribe_factory.build(cfg.transcribe),
        matcher=time_match_factory.build(cfg.time_match),
        extractor=metadata_factory.build(cfg.metadata),
        builder=timeline_factory.build_builder(cfg.timeline),
        serializer=timeline_factory.build_serializer(cfg.timeline),
        labeler=llm_factory.build(cfg.llm),
    )


def run(
    url: str,
    cfg: ExperimentConfig,
    from_step: str | None = None,
    refetch: bool = False,
    on_step: OnStep | None = None,
) -> RunSummary:
    if from_step is not None and from_step not in STEPS:
        raise ValueError(f"unknown step '{from_step}'; valid: {', '.join(STEPS)}")
    video_id = extract_video_id(url)
    if video_id is None:
        raise StepError("ingest", f"not a YouTube video URL: {url}")

    steps = build_steps(cfg)
    out_dir = Path(cfg.outputs_dir) / video_id
    first = STEPS.index(from_step) if from_step else 0
    started_at = utc_now()
    ran: list[str] = []
    reloaded: list[str] = []
    notify = on_step or (lambda step, status: None)

    def stage(name: str, compute: Callable[[], Any]) -> Any:
        if STEPS.index(name) < first:
            path = out_dir / f"{STEP_FILES[name]}.json"
            if not path.exists():
                raise StepError(
                    name, f"no saved output at {path}; rerun with --from-step {name} or earlier"
                )
            value = load_step(out_dir, STEP_FILES[name], STEP_TYPES[name])
            reloaded.append(name)
            notify(name, "reloaded")
            return value

        notify(name, "running")
        try:
            value = compute()
        except StepError:
            raise
        except Exception as exc:
            raise StepError(name, f"{type(exc).__name__}: {exc}") from exc
        save_step(out_dir, STEP_FILES[name], value)
        ran.append(name)
        notify(name, "done")
        return value

    track: IngestedTrack = stage("ingest", lambda: steps.ingester.ingest(url))
    fetched: LyricsFetchResult = stage(
        "lyrics", lambda: fetch_all(steps.fetchers, track, cfg.lyrics.cache_dir, refetch)
    )
    transcript: Transcript = stage("transcribe", lambda: steps.transcriber.transcribe(track))
    synced: SyncedLyrics = stage(
        "time_match", lambda: steps.matcher.match(track, fetched.candidates, transcript)
    )
    if "time_match" in ran and cfg.time_match.write_click_track:
        _write_click_tracks(track, synced, out_dir)

    meta: TrackMetadata = stage("metadata", lambda: steps.extractor.extract(track))
    timeline: Timeline = stage("timeline", lambda: steps.builder.build(track, synced, meta))

    # Always re-serialized (deterministic), so the LLM sees the *configured* serializer's
    # output even when the timeline itself was reloaded.
    serialized = steps.serializer.serialize(timeline)
    (out_dir / f"timeline.{steps.serializer.extension}").write_text(serialized)

    result: StructureResult = stage(
        "llm", lambda: steps.labeler.label(timeline, serialized, cfg.timeline.serializer)
    )
    (out_dir / "summary.md").write_text(
        build_summary(timeline.header.title or video_id, result, synced, meta)
    )

    summary = RunSummary(
        video_id=video_id,
        steps_run=ran,
        steps_reloaded=reloaded,
        config=cfg.model_dump(),
        started_at=started_at,
        finished_at=utc_now(),
    )
    save_step(out_dir, "run", summary)
    return summary


def _write_click_tracks(track: IngestedTrack, synced: SyncedLyrics, out_dir: Path) -> None:
    starts = [segment.start for segment in synced.segments]
    write_click_track(track.path, starts, out_dir / "clicks.wav")
    if synced.verdict == "offset_corrected":
        raw_starts = [start - synced.offset_applied_s for start in starts]
        write_click_track(track.path, raw_starts, out_dir / "clicks_raw.wav")
