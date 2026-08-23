import json

import pytest

from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.manifest import (
    ManifestEntry,
    read_manifest_entry,
    write_manifest_entry,
)


@pytest.fixture
def manifest_dir(tmp_path):
    return tmp_path / "manifest"


@pytest.fixture
def config(manifest_dir):
    return DownloadConfig(manifest_dir=str(manifest_dir))


def _make_entry(video_id="abc123", path="music/track.mp3", **overrides):
    defaults = dict(
        video_id=video_id,
        path=path,
        title="Some Title",
        uploader="Some Uploader",
        duration=180.0,
        first_run_id="run-1",
        downloaded_at="2026-08-23T00:00:00+00:00",
    )
    defaults.update(overrides)
    return ManifestEntry(**defaults)


def test_round_trip_read_after_write(config, tmp_path):
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    entry = _make_entry(path=str(real_file))

    write_manifest_entry(entry, config)
    result = read_manifest_entry(entry.video_id, config)

    assert result == entry


def test_write_leaves_no_temp_files_behind(config, tmp_path, manifest_dir):
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    entry = _make_entry(path=str(real_file))

    write_manifest_entry(entry, config)

    assert list(manifest_dir.iterdir()) == [manifest_dir / f"{entry.video_id}.json"]


def test_missing_file_returns_none(config):
    assert read_manifest_entry("nonexistent", config) is None


def test_malformed_json_returns_none(config, manifest_dir):
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "broken.json").write_text("{not valid json")

    assert read_manifest_entry("broken", config) is None


def test_missing_required_key_returns_none(config, manifest_dir):
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "incomplete.json").write_text(json.dumps({"video_id": "incomplete"}))

    assert read_manifest_entry("incomplete", config) is None


def test_entry_whose_path_no_longer_exists_returns_none(config, tmp_path):
    missing_path = tmp_path / "deleted.mp3"
    entry = _make_entry(video_id="ghost", path=str(missing_path))

    write_manifest_entry(entry, config)

    assert not missing_path.exists()
    assert read_manifest_entry("ghost", config) is None
