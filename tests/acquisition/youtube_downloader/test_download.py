import pytest

from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.download import download_tracks
from acquisition.youtube_downloader.schema import DownloadedTrack, DownloadFailure


def _fake_worker_success(url, config, run_id):
    return DownloadedTrack(
        url=url, path=f"music/{url}.mp3", video_id=url, title=url, uploader=None, duration=1.0
    )


def _fake_worker_failure(url, config, run_id):
    return DownloadFailure(url=url, error="boom", error_type="RuntimeError")


def test_dispatch_order_and_result_collection():
    urls = ["a", "b", "c"]
    result = download_tracks(urls, DownloadConfig(), _worker=_fake_worker_success)

    assert [t.url for t in result.tracks] == urls
    assert result.failures == []


def test_partial_failure_collection():
    def worker(url, config, run_id):
        if url == "bad":
            return _fake_worker_failure(url, config, run_id)
        return _fake_worker_success(url, config, run_id)

    result = download_tracks(["good", "bad", "good2"], DownloadConfig(), _worker=worker)

    assert [t.url for t in result.tracks] == ["good", "good2"]
    assert [f.url for f in result.failures] == ["bad"]


def test_progress_callback_fires_started_then_completed_or_failed():
    events = []

    def worker(url, config, run_id):
        if url == "bad":
            return _fake_worker_failure(url, config, run_id)
        return _fake_worker_success(url, config, run_id)

    def on_progress(url, status):
        events.append((url, status))

    download_tracks(["ok", "bad"], DownloadConfig(), on_progress=on_progress, _worker=worker)

    assert events == [
        ("ok", "started"),
        ("ok", "completed"),
        ("bad", "started"),
        ("bad", "failed"),
    ]


def test_run_id_seam_propagates_to_result_and_worker():
    seen_run_ids = []

    def worker(url, config, run_id):
        seen_run_ids.append(run_id)
        return _fake_worker_success(url, config, run_id)

    result = download_tracks(["a"], DownloadConfig(), _worker=worker, _run_id="fixed-run-id")

    assert result.run_id == "fixed-run-id"
    assert seen_run_ids == ["fixed-run-id"]


def test_run_id_auto_generated_when_not_overridden():
    result_a = download_tracks(["a"], DownloadConfig(), _worker=_fake_worker_success)
    result_b = download_tracks(["a"], DownloadConfig(), _worker=_fake_worker_success)

    assert result_a.run_id != result_b.run_id


def test_on_progress_exception_propagates():
    def raising_progress(url, status):
        raise ValueError("callback bug")

    with pytest.raises(ValueError, match="callback bug"):
        download_tracks(
            ["a"], DownloadConfig(), on_progress=raising_progress, _worker=_fake_worker_success
        )


def test_same_url_twice_calls_worker_twice_no_dedup():
    calls = []

    def worker(url, config, run_id):
        calls.append(url)
        return _fake_worker_success(url, config, run_id)

    result = download_tracks(["dup", "dup"], DownloadConfig(), _worker=worker)

    assert calls == ["dup", "dup"]
    assert len(result.tracks) == 2
