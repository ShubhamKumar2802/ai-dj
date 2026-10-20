import shutil

import numpy as np

from experiments.vocal_free_windows.stem_cache import get_or_separate


class FakeSeparator:
    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return np.full((480, 2), 0.25, dtype=np.float32)


def _audio(tmp_path, name="track.mp3", content=b"fake audio bytes"):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_rerun_hits_cache(tmp_path):
    sep = FakeSeparator()
    audio = _audio(tmp_path)
    first = get_or_separate(audio, "htdemucs|v1", tmp_path / "cache", sep)
    second = get_or_separate(audio, "htdemucs|v1", tmp_path / "cache", sep)
    assert len(sep.calls) == 1
    assert second.shape == (480, 2)
    np.testing.assert_allclose(first, second, atol=1 / 32768)


def test_separator_changed_reseparates(tmp_path):
    sep = FakeSeparator()
    audio = _audio(tmp_path)
    get_or_separate(audio, "htdemucs|v1", tmp_path / "cache", sep)
    get_or_separate(audio, "htdemucs_ft|v1", tmp_path / "cache", sep)
    assert len(sep.calls) == 2


def test_renamed_file_hits_cache(tmp_path):
    sep = FakeSeparator()
    audio = _audio(tmp_path)
    get_or_separate(audio, "htdemucs|v1", tmp_path / "cache", sep)
    renamed = tmp_path / "renamed.mp3"
    shutil.move(audio, renamed)
    get_or_separate(str(renamed), "htdemucs|v1", tmp_path / "cache", sep)
    assert len(sep.calls) == 1


def test_no_temp_files_left(tmp_path):
    get_or_separate(_audio(tmp_path), "v", tmp_path / "cache", FakeSeparator())
    assert [p.suffix for p in (tmp_path / "cache").iterdir()] == [".wav"]
    assert not any("tmp" in p.name for p in (tmp_path / "cache").iterdir())
