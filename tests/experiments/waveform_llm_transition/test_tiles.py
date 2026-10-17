import matplotlib.image as mpimg
import numpy as np
import pytest

from experiments.waveform_llm_transition.bands import BandEnvelopes
from experiments.waveform_llm_transition.schema import TrackFacts
from experiments.waveform_llm_transition.tiles import draw_tile, header_text, tile_windows


def test_tiling_a_track():
    windows = tile_windows(208, tile_s=60, overlap_s=8)
    assert [(w.start, w.end) for w in windows] == [(0, 60), (52, 112), (104, 164), (156, 208)]
    assert windows[0].start == 0 and windows[-1].end == 208
    for prev, cur in zip(windows, windows[1:]):
        assert prev.end - cur.start == 8
    assert [w.label for w in windows][1] == "tile 2/4 (0:52–1:52)"


def test_short_track_is_one_tile():
    windows = tile_windows(45, tile_s=60, overlap_s=8)
    assert [(w.start, w.end, w.count) for w in windows] == [(0, 45, 1)]


def test_bad_overlap_rejected():
    with pytest.raises(ValueError):
        tile_windows(208, tile_s=60, overlap_s=60)


def _facts(duration: float) -> TrackFacts:
    return TrackFacts(
        label="A",
        name="Synthetic",
        path="x.mp3",
        duration=duration,
        bpm=110.0,
        lufs=-9.1,
        downbeats=list(np.arange(0.5, duration, 240 / 110)),
        downbeat_confidence=0.6,
    )


def test_header_has_every_fact():
    facts = _facts(208)
    text = header_text(facts, tile_windows(208, 60, 8)[1])
    for part in ("A: Synthetic", "110.0 BPM", "3:28", "-9.1 LUFS", "tile 2/4 (0:52–1:52)"):
        assert part in text


def test_last_tile_keeps_pixel_size(tmp_path):
    duration = 75.0
    rng = np.random.default_rng(0)
    cols = int(duration * 25)
    env = BandEnvelopes(*(rng.random(cols) for _ in range(3)), px_per_s=25)
    facts = _facts(duration)
    windows = tile_windows(duration, 60, 8)
    sizes = []
    for w in windows:
        out_path = tmp_path / f"{w.index}.png"
        path = draw_tile(env, facts, w, tile_s=60, height_px=600, out_path=out_path)
        sizes.append(mpimg.imread(path).shape[:2])
    assert sizes == [(600, 1500)] * len(windows)
