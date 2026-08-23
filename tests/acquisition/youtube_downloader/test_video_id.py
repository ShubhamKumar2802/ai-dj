import pytest

from acquisition.youtube_downloader.video_id import extract_video_id

_ID = "dQw4w9WgXcQ"

_RECOGNIZED = [
    f"https://www.youtube.com/watch?v={_ID}",
    f"https://youtube.com/watch?v={_ID}",
    f"https://www.youtube.com/watch?v={_ID}&list=PL123&index=5",
    f"https://youtu.be/{_ID}",
    f"https://youtu.be/{_ID}/",
    f"https://youtu.be/{_ID}?t=30",
    f"https://www.youtube.com/shorts/{_ID}",
    f"https://www.youtube.com/shorts/{_ID}/",
    f"https://youtube.com/embed/{_ID}",
    f"https://www.youtube.com/embed/{_ID}?rel=0",
]

_UNRECOGNIZED = [
    f"https://music.youtube.com/watch?v={_ID}",
    "https://www.youtube.com/playlist?list=PL123",
    _ID,
    "",
    "not a url",
    "https://example.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch",
]


@pytest.mark.parametrize("url", _RECOGNIZED)
def test_recognized_url_shapes_extract_the_id(url):
    assert extract_video_id(url) == _ID


@pytest.mark.parametrize("url", _UNRECOGNIZED)
def test_unrecognized_shapes_return_none(url):
    assert extract_video_id(url) is None
