"""Runs the fetcher chain with a per-(video, source) disk cache (spec §4.2, §4.3).

Fetched lyrics aren't a function of the audio (an external database can change at any
time), so the key is `(video_id, source, FETCHER_VERSION)`; the cache only exists so
reruns don't hammer the APIs. `refetch=True` bypasses it.
"""

import json
from pathlib import Path

from experiments.lyrics_sourcing.persistence import from_dict, to_jsonable
from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    LyricsCandidate,
    LyricsFetchResult,
    utc_now,
)
from experiments.lyrics_sourcing.steps.lyrics.interface import LyricsFetcher

FETCHER_VERSION = "1"


def fetch_all(
    fetchers: list[LyricsFetcher],
    track: IngestedTrack,
    cache_dir: str | Path,
    refetch: bool = False,
) -> LyricsFetchResult:
    """Every fetcher runs, in priority order, even after one succeeds. A fetcher that
    raises becomes one `status="error"` candidate — it never aborts the run.
    """
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)

    candidates: list[LyricsCandidate] = []
    for fetcher in fetchers:
        path = cache_root / f"{track.video_id}_{fetcher.source}_{FETCHER_VERSION}.json"
        if path.exists() and not refetch:
            candidates.extend(from_dict(list[LyricsCandidate], json.loads(path.read_text())))
            continue

        try:
            fetched = fetcher.fetch(track)
        except Exception as exc:  # network/API failures of every shape
            candidates.append(_error(fetcher.source, f"{type(exc).__name__}: {exc}"))
            continue  # errors aren't cached: a retry should actually retry

        path.write_text(json.dumps(to_jsonable(fetched), indent=2, ensure_ascii=False))
        candidates.extend(fetched)

    return LyricsFetchResult(candidates=candidates)


def _error(source: str, message: str) -> LyricsCandidate:
    return LyricsCandidate(
        source=source,
        source_ref=None,
        status="error",
        lines=[],
        plain_text=None,
        reference_duration=None,
        error=message,
        fetched_at=utc_now(),
    )
