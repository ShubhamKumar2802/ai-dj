"""Live-network smoke test — skip-guarded by default (spec §8).

Unlike ingestion/orchestrator's music/-presence guard, there's no local signal
for "network + real YouTube is available and desired right now" — running
live network calls by default would make the default suite flaky and slow.

Run explicitly with:
    AI_DJ_RUN_LIVE_YOUTUBE_TESTS=1 uv run pytest \
        tests/acquisition/youtube_downloader/test_real_download_smoke.py -v
"""

import os

import librosa
import pytest

from acquisition.youtube_downloader.config import DownloadConfig
from acquisition.youtube_downloader.download import download_tracks
from acquisition.youtube_downloader.manifest import read_manifest_entry
from acquisition.youtube_downloader.video_id import extract_video_id

pytestmark = pytest.mark.skipif(
    os.environ.get("AI_DJ_RUN_LIVE_YOUTUBE_TESTS") != "1",
    reason="live YouTube network test — opt in via AI_DJ_RUN_LIVE_YOUTUBE_TESTS=1",
)

# "Me at the zoo" — the first video ever uploaded to YouTube, about as
# permanent/stable a public URL as exists on the platform.
_TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def test_real_download_then_manifest_hit_on_second_call(tmp_path):
    config = DownloadConfig(
        output_dir=str(tmp_path / "music"), manifest_dir=str(tmp_path / "manifest")
    )
    video_id = extract_video_id(_TEST_URL)

    first = download_tracks([_TEST_URL], config)

    assert len(first.tracks) == 1
    assert first.failures == []
    track = first.tracks[0]
    assert os.path.isfile(track.path)
    assert os.path.getsize(track.path) > 0

    audio, _ = librosa.load(track.path, sr=None, duration=1.0)
    assert len(audio) > 0

    entry_after_first = read_manifest_entry(video_id, config)
    assert entry_after_first is not None
    first_run_id = entry_after_first.first_run_id

    second = download_tracks([_TEST_URL], config)

    assert len(second.tracks) == 1
    assert second.failures == []
    assert second.run_id != first.run_id

    entry_after_second = read_manifest_entry(video_id, config)
    assert entry_after_second.first_run_id == first_run_id
