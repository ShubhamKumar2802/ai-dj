import dataclasses
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from acquisition.youtube_downloader.config import DownloadConfig


@dataclass
class ManifestEntry:
    video_id: str
    path: str
    title: str
    uploader: str | None
    duration: float
    first_run_id: str
    downloaded_at: str


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _entry_path(video_id: str, config: DownloadConfig) -> Path:
    return Path(config.manifest_dir) / f"{video_id}.json"


def read_manifest_entry(video_id: str, config: DownloadConfig) -> ManifestEntry | None:
    path = _entry_path(video_id, config)
    try:
        data = json.loads(path.read_text())
        entry = ManifestEntry(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        return None

    if not Path(entry.path).exists():
        return None

    return entry


def write_manifest_entry(entry: ManifestEntry, config: DownloadConfig) -> None:
    path = _entry_path(entry.video_id, config)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    tmp_path.write_text(json.dumps(dataclasses.asdict(entry)))
    tmp_path.replace(path)
