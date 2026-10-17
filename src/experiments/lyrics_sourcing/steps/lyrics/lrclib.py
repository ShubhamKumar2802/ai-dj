"""LRCLIB public API (spec §4.2). No auth; identifying User-Agent; rate-limited."""

import re
import time

from experiments.lyrics_sourcing.config import LyricsConfig
from experiments.lyrics_sourcing.schema import IngestedTrack, LyricsCandidate, utc_now
from experiments.lyrics_sourcing.steps.lyrics.lrc import parse_lrc

SOURCE = "lrclib"

_NOISE = (
    "official music video",
    "official video",
    "full video song",
    "full video",
    "video song",
    "lyrical video",
    "lyrical",
    "full song",
    "full audio",
    "audio",
    "hd",
    "4k",
)
_BRACKETED = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")
_NOISE_PATTERN = re.compile(r"\b(" + "|".join(re.escape(n) for n in _NOISE) + r")\b", re.I)


def clean_title(raw_title: str) -> str:
    """Crude video-title -> search-query cleanup (spec §4.2; §9 Q2 measures if it's enough)."""
    title = _BRACKETED.sub(" ", raw_title)
    title = title.split("|")[0]
    title = _NOISE_PATTERN.sub(" ", title)
    title = re.sub(r"[\"'“”‘’]", "", title)
    title = re.sub(r"\s+-\s+|\s*-\s*$", " ", title)
    return re.sub(r"\s+", " ", title).strip()


class LrclibFetcher:
    source = SOURCE

    def __init__(self, cfg: LyricsConfig) -> None:
        self._cfg = cfg
        self._last_request = 0.0

    def fetch(self, track: IngestedTrack) -> list[LyricsCandidate]:
        import httpx  # lazy: keeps factory construction import-free

        headers = {"User-Agent": self._cfg.lrclib_user_agent}
        with httpx.Client(base_url=self._cfg.lrclib_base_url, headers=headers, timeout=20) as c:
            if track.title and track.artist and track.album:
                response = self._get(
                    c,
                    "/api/get",
                    {
                        "track_name": track.title,
                        "artist_name": track.artist,
                        "album_name": track.album,
                        "duration": round(track.duration),
                    },
                )
                if response.status_code == 200:
                    candidate = parse_lrclib_record(response.json())
                    if candidate.status == "synced":
                        return [candidate]

            if track.title and track.artist:
                params = {"track_name": track.title, "artist_name": track.artist}
            else:
                params = {"q": clean_title(track.raw_title)}
            response = self._get(c, "/api/search", params)
            response.raise_for_status()
            return parse_lrclib_search(response.json(), self._cfg.lrclib_max_candidates)

    def _get(self, client, path: str, params: dict):
        wait = self._cfg.lrclib_min_interval_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            return client.get(path, params=params)
        finally:
            self._last_request = time.monotonic()


def parse_lrclib_record(record: dict) -> LyricsCandidate:
    """One LRCLIB record -> candidate. Pure. Duration is recorded, never used to filter."""
    base = {
        "source": SOURCE,
        "source_ref": str(record["id"]) if record.get("id") is not None else None,
        "reference_duration": record.get("duration"),
        "fetched_at": utc_now(),
    }
    if record.get("instrumental"):
        return LyricsCandidate(
            **base, status="not_found", lines=[], plain_text=None, error="instrumental"
        )

    synced = record.get("syncedLyrics") or ""
    lines = parse_lrc(synced) if synced.strip() else []
    if lines:
        return LyricsCandidate(**base, status="synced", lines=lines, plain_text=None, error=None)

    plain = record.get("plainLyrics") or ""
    if plain.strip():
        return LyricsCandidate(**base, status="plain_only", lines=[], plain_text=plain, error=None)
    return LyricsCandidate(**base, status="not_found", lines=[], plain_text=None, error=None)


def parse_lrclib_search(results: list[dict], max_candidates: int) -> list[LyricsCandidate]:
    """Up to `max_candidates` synced results in LRCLIB's order; else one plain/not_found. Pure."""
    candidates = [parse_lrclib_record(record) for record in results]
    synced = [c for c in candidates if c.status == "synced"][:max_candidates]
    if synced:
        return synced

    plain = [c for c in candidates if c.status == "plain_only"]
    if plain:
        return plain[:1]
    return [
        LyricsCandidate(
            source=SOURCE,
            source_ref=None,
            status="not_found",
            lines=[],
            plain_text=None,
            reference_duration=None,
            error=None,
            fetched_at=utc_now(),
        )
    ]
