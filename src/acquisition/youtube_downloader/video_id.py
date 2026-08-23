from urllib.parse import parse_qs, urlparse

_WATCH_HOSTS = {"youtube.com", "www.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_ID_PREFIXES = ("/shorts/", "/embed/")


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    if host in _SHORT_HOSTS:
        segment = path.lstrip("/").split("/")[0]
        return segment or None

    if host in _WATCH_HOSTS:
        if path == "/watch":
            values = parse_qs(parsed.query).get("v")
            return values[0] if values else None

        for prefix in _PATH_ID_PREFIXES:
            if path.startswith(prefix.rstrip("/")):
                remainder = path[len(prefix.rstrip("/")) :].lstrip("/")
                segment = remainder.split("/")[0]
                return segment or None

    return None
