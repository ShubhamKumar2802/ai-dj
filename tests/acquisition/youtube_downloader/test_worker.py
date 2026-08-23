import acquisition.youtube_downloader.worker as worker_module
from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.manifest import (
    ManifestEntry,
    read_manifest_entry,
    write_manifest_entry,
)
from acquisition.youtube_downloader.schema import DownloadedTrack, DownloadFailure
from acquisition.youtube_downloader.worker import _download_one

_URL = "https://youtu.be/abc123"


def test_manifest_hit_short_circuits_without_calling_downloader(
    tmp_path, make_fake_downloader, make_download_info
):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")

    cached_info = make_download_info(path=str(real_file), video_id="abc123")
    write_manifest_entry(
        ManifestEntry(
            video_id=cached_info.video_id,
            path=cached_info.path,
            title=cached_info.title,
            uploader=cached_info.uploader,
            duration=cached_info.duration,
            first_run_id="run-0",
            downloaded_at="2026-08-23T00:00:00+00:00",
        ),
        config,
    )

    downloader = make_fake_downloader()
    result = _download_one(_URL, config, run_id="run-1", _downloader=downloader)

    assert downloader.calls == []
    assert isinstance(result, DownloadedTrack)
    assert result.path == str(real_file)
    assert result.video_id == "abc123"


def test_manifest_miss_downloads_and_writes_entry(
    tmp_path, make_fake_downloader, make_download_info
):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    info = make_download_info(path=str(real_file), video_id="abc123")
    downloader = make_fake_downloader(result=info)

    result = _download_one(_URL, config, run_id="run-1", _downloader=downloader)

    assert len(downloader.calls) == 1
    assert isinstance(result, DownloadedTrack)
    assert result.path == str(real_file)

    entry = read_manifest_entry("abc123", config)
    assert entry is not None
    assert entry.first_run_id == "run-1"


def test_corrupted_manifest_entry_degrades_to_fresh_download(
    tmp_path, make_fake_downloader, make_download_info
):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "abc123.json").write_text("{not valid json")

    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    info = make_download_info(path=str(real_file), video_id="abc123")
    downloader = make_fake_downloader(result=info)

    result = _download_one(_URL, config, run_id="run-2", _downloader=downloader)

    assert len(downloader.calls) == 1
    assert isinstance(result, DownloadedTrack)

    entry = read_manifest_entry("abc123", config)
    assert entry.first_run_id == "run-2"


def test_write_failure_after_successful_download_surfaces_as_failure(
    tmp_path, monkeypatch, make_fake_downloader, make_download_info
):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    info = make_download_info(path=str(real_file), video_id="abc123")
    downloader = make_fake_downloader(result=info)

    def _raise(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(worker_module, "write_manifest_entry", _raise)

    result = _download_one(_URL, config, run_id="run-1", _downloader=downloader)

    assert isinstance(result, DownloadFailure)
    assert result.error_type == "OSError"


def test_downloader_exception_becomes_download_failure(tmp_path, make_fake_downloader):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    downloader = make_fake_downloader(error=RuntimeError("network blew up"))

    result = _download_one(_URL, config, run_id="run-1", _downloader=downloader)

    assert isinstance(result, DownloadFailure)
    assert result.url == _URL
    assert result.error == "network blew up"
    assert result.error_type == "RuntimeError"


def test_unrecognized_url_always_downloads_fresh(
    tmp_path, make_fake_downloader, make_download_info
):
    config = DownloadConfig(manifest_dir=str(tmp_path / "manifest"))
    real_file = tmp_path / "track.mp3"
    real_file.write_text("fake audio")
    info = make_download_info(path=str(real_file), video_id="abc123")
    downloader = make_fake_downloader(result=info)

    unrecognized_url = "https://example.com/not-youtube"
    result = _download_one(unrecognized_url, config, run_id="run-1", _downloader=downloader)

    assert len(downloader.calls) == 1
    assert isinstance(result, DownloadedTrack)
    assert result.url == unrecognized_url

    entry = read_manifest_entry("abc123", config)
    assert entry is not None
