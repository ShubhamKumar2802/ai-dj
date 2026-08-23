from urllib.parse import parse_qs, urlparse

import yt_dlp

from acquisition.youtube_downloader.config import DownloadConfig

_HOSTS = {"youtube.com", "www.youtube.com"}


def extract_playlist_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in _HOSTS:
        return None

    values = parse_qs(parsed.query).get("list")
    return values[0] if values else None


def expand_playlist_url(url: str, config: DownloadConfig) -> list[str] | None:
    playlist_id = extract_playlist_id(url)
    if playlist_id is None:
        return None

    canonical_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    options = {"extract_flat": True, "quiet": True, "retries": config.retries}

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(canonical_url, download=False)

    entries = info.get("entries") or []
    return [entry["url"] for entry in entries if entry]
